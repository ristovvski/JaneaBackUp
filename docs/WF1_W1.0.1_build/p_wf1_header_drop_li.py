#!/usr/bin/env python3
"""WF-1 team alert: drop the LinkedIn link from the HEADER. The Details block already carries it.

One-line change to `M7 Build`'s headline: remove `+ aLiLink`. Everything else is untouched -
header keeps name (title @ company) · campaign · via sender — Open lead, and the Details block is
unchanged. WF-2's email header has no LinkedIn button, so it is not touched at all.

Static runs on the REAL Person-83a12921 payload pulled from its own execution, not a synthetic one,
and asserts both directions: the LinkedIn URL is gone from the header line, and still present in the
Details block. Checking only the first would pass a build that dropped the link entirely.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"


def n8n(path, q=None, method="GET", body=None, attempt=0):
    import time
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# ---- find the real Jerod payload
print("locating the Person-83a12921 execution...")
lead = None
ex = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 60})
for e in (ex.get("data") or []):
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        j = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    L = j.get("lead") or {}
    if "jerod" in str(L.get("full_name", "")).lower():
        lead = L
        print(f"   exec {e['id']} {e.get('startedAt')}  {L.get('full_name')!r}")
        break
if not lead:
    print("   Jerod execution not found in the last 60 - falling back to the most recent WF-1 reply")
    for e in (ex.get("data") or []):
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "M7 Build" not in rd:
            continue
        lead = (rd["Normalize"][0]["data"]["main"][0][0]["json"] or {}).get("lead")
        print(f"   using exec {e['id']} {(lead or {}).get('full_name')!r}")
        break
if not lead:
    raise SystemExit("no WF-1 reply payload available - refusing to test on a synthetic one")
print(f"   payload: name={lead.get('full_name')!r} company={lead.get('company_name')!r} "
      f"profile={str(lead.get('profile_url'))[:52]!r}")

wf = n8n(f"/api/v1/workflows/{WF1}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
src = N["M7 Build"]["parameters"]["jsCode"]
if "__headline" not in src:
    raise SystemExit("M7 Build has no __headline - run the Details-block patch first")
i = src.find("const __headline = ")
j = src.find(";\n", i)
stmt = src[i:j + 1]
if "aLiLink" not in stmt:
    print("\n(header already has no LinkedIn link - nothing to change)")
    new = src
    changed = False
else:
    new_stmt = stmt.replace(" + aLiLink", "")
    if "aLiLink" in new_stmt:
        raise SystemExit("aLiLink survived removal - refusing to deploy a half-edit")
    new = src[:i] + new_stmt + src[j + 1:]
    changed = True
    print(f"\nheadline before: {stmt.strip()[:150]}")
    print(f"headline after : {new_stmt.strip()[:150]}")

# ---- static on the real payload
HARNESS = """
const NORM = __NORM__;
const $ = (nm) => { if (nm === 'Normalize') return { item: { json: NORM } };
                    throw new Error('absent ' + nm); };
const escapeSlack = (s) => String(s ?? '');
const aName = NORM.lead.full_name, aCo = NORM.lead.company_name, aLi = NORM.lead.profile_url;
const aParen = aCo ? (' (@ ' + aCo + ')') : '';
const aMetaStr = ' \\u00b7 CampaignX \\u00b7 via Mario';
const aLead = '<https://pd/leads/inbox/L1|Open lead>';
const aLiLink = aLi ? ' \\u00b7 <' + aLi + '|LinkedIn>' : '';
__BODY__
const parts = alert_text.split('\\n*Details:*\\n');
console.log(JSON.stringify({ header: parts[0], details: parts[1] || '' }));
"""
body_start = new.find("const __headline = ")
body_end = new.find("const alert_text = ", body_start)
body_end = new.find(";\n", body_end) + 1
snippet = new[body_start:body_end]

tmp = os.path.join(HERE, "_hdr_case.js")
with open(tmp, "w", encoding="utf-8") as f:
    f.write(HARNESS.replace("__NORM__", json.dumps({"lead": lead}))
                   .replace("__BODY__", snippet))
p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
os.remove(tmp)
if p.returncode != 0:
    raise SystemExit(f"static FAILED: {(p.stderr or '').strip()[-300:]}")
out = json.loads(p.stdout.strip())
li = str(lead.get("profile_url") or "")
checks = {
    "header has NO LinkedIn link": ("|LinkedIn>" not in out["header"]),
    "header still has Open lead": ("Open lead" in out["header"]),
    "header still has name": (str(lead.get("full_name") or "") in out["header"]),
    "Details block STILL has the LinkedIn profile": (bool(li) and li in out["details"]),
    "Details block still has Name": ("Name: " in out["details"]),
}
print("\n--- static on the real payload ---")
for k, v in checks.items():
    print(f"  [{'OK ' if v else 'RED'}] {k}")
print(f"\n  header : {out['header'][:160]!r}")
print(f"  details: {out['details'][:160]!r}")
if not all(checks.values()):
    sys.exit(1)
if not changed:
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_hdrli_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["M7 Build"]["parameters"]["jsCode"] = new
d = stripped_keys(wf)
if d:
    print(f"stripping {d}")
n8n(f"/api/v1/workflows/{WF1}", None, "PUT", put_body(wf))

after = n8n(f"/api/v1/workflows/{WF1}")
x = {n["name"]: n for n in after["nodes"]}["M7 Build"]["parameters"]["jsCode"]
hi = x.find("const __headline = ")
hstmt = x[hi:x.find(";\n", hi) + 1]
problems = []
if "aLiLink" in hstmt:
    problems.append("header still contains aLiLink")
if "Details" not in x:
    problems.append("Details block missing")
if after.get("active") is not ORIG.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for pr in problems:
    print("  -", pr)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
sys.exit(1 if problems else 0)
