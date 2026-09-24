#!/usr/bin/env python3
"""1(b) CLASS FIX, WF-1 — same blindness as WF-2 had: `Lead Search` asks only about LEADS, and a
person converted to an open DEAL has none. Rule 0 ("create") therefore fires for exactly the people
who are furthest along.

  + Deal Search      GET /api/v2/deals?person_id&status=open, inserted PID Resolved -> Lead Search
  ~ Lead Search      person_id read from $('PID Resolved') BY NAME - the insert shifts $json, and
                     leaving it positional would have made Lead Search query the DEALS response
  ~ Lead Create Gate rule 0 gains "no open deal AND the deal check succeeded"

Rules 0 and 1 are exact complements, so a person with an open deal and no matching lead now matches
NEITHER and lands on the existing `extra` fallback (Lead Resp Invalid) - no creation, and visible
rather than silent. Unknown deal state also blocks creation: write gates fail closed (9b.0f).

NOT done here, and stated rather than hidden: WF-1 does not yet WRITE the activity onto the deal the
way WF-2 now does. This stops the duplicate; routing the record to its right home on WF-1's sent
path is a follow-up.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, att=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF1}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.setdefault("connections", {})
if "Deal Search" in N:
    sys.exit("Deal Search already present - nothing to do")

px, py = N["PID Resolved"]["position"]
wf["nodes"].append({
    "parameters": {"method": "GET",
                   "url": "=https://api.pipedrive.com/api/v2/deals"
                          "?person_id={{ $json.person_id }}&status=open&limit=50",
                   "authentication": "predefinedCredentialType",
                   "nodeCredentialType": "pipedriveApi", "options": {}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "position": [px + 112, py + 190], "id": "wf1-dealguard-0001", "name": "Deal Search",
    "credentials": N["Lead Search"].get("credentials"),
    "onError": "continueRegularOutput"})
C["PID Resolved"] = {"main": [[{"node": "Deal Search", "type": "main", "index": 0}]]}
C["Deal Search"] = {"main": [[{"node": "Lead Search", "type": "main", "index": 0}]]}

ls = N["Lead Search"]["parameters"]
OLDU = "=https://api.pipedrive.com/v1/leads?person_id={{ $json.person_id }}"
if ls.get("url") != OLDU:
    sys.exit(f"Lead Search url not as expected: {ls.get('url')!r}")
ls["url"] = ("=https://api.pipedrive.com/v1/leads"
             "?person_id={{ $('PID Resolved').item.json.person_id }}")

DEALJS = (" && (() => { const r = $('Deal Search').item.json;"
          " if (!r || r.success === false) return false;"
          " const d = Array.isArray(r.data) ? r.data : (Array.isArray(r) ? r : null);"
          " if (d === null) return false;"
          " return !d.some(x => String((x || {}).status || '') === 'open'); })()")
g = N["Lead Create Gate"]["parameters"]
rule0 = g["rules"]["values"][0]["conditions"]["conditions"][0]
lv = rule0["leftValue"]
if not lv.endswith(" }}"):
    sys.exit("rule 0 expression shape unexpected")
if "Deal Search" in lv:
    sys.exit("rule 0 already guarded")
rule0["leftValue"] = lv[:-3] + DEALJS + " }}"

print("--- statics: rule 0 under four shapes ---")
inner = rule0["leftValue"].strip()[2:-2].strip()
if inner.startswith("{"):
    inner = inner[1:]
if inner.endswith("}"):
    inner = inner[:-1]
ok = True
CASES = [
    ("ANDREA SHAPE: 0 leads + OPEN DEAL -> must NOT create", [], [{"status": "open", "id": 2093}],
     True, False),
    ("0 leads, no deals -> creates as before (no regression)", [], [], True, True),
    ("deal lookup FAILED -> must NOT create (fail closed)", [], None, True, False),
    ("matching lead exists, no deal -> rule 0 false as before",
     [{"is_archived": False, "F_CAMP": "HumanX"}], [], True, False),
    ("closed deal only -> creates (a won/lost deal is not active representation)", [],
     [{"status": "won", "id": 7}], True, True),
]
for label, leads, deals, success, want in CASES:
    dealresp = ("{ success: false }" if deals is None
                else json.dumps({"success": True, "data": deals}))
    src = f"""
const CFG = {{ fields: {{ lead_campaign: 'F_CAMP' }} }};
const NORM = {{ campaign: {{ name: 'HumanX' }} }};
const $json = {json.dumps({"success": success, "data": leads})};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Deal Search') return {{ item: {{ json: {dealresp} }} }};
  throw new Error('absent ' + nm);
}};
console.log(JSON.stringify({{ v: ({inner}) }}));
"""
    tmp = os.path.join(HERE, "_wf1dg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}\n         {(p.stderr or '').strip()[:260]}")
        ok = False
        continue
    v = json.loads(p.stdout.strip().splitlines()[-1])["v"]
    good = v is want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  creates={v} (want {want})")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_dealguard_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
if "Deal Search" not in AN:
    problems.append("Deal Search missing")
if AN.get("Deal Search", {}).get("onError") != "continueRegularOutput":
    problems.append("Deal Search is BLOCKING the sent path")
pr = [c.get("node") for g_ in (AC.get("PID Resolved") or {}).get("main", []) for c in (g_ or [])]
ds = [c.get("node") for g_ in (AC.get("Deal Search") or {}).get("main", []) for c in (g_ or [])]
if pr != ["Deal Search"] or ds != ["Lead Search"]:
    problems.append(f"chain wrong: PID Resolved->{pr}, Deal Search->{ds}")
if "$('PID Resolved').item.json.person_id" not in AN["Lead Search"]["parameters"]["url"]:
    problems.append("Lead Search still reads person_id positionally")
if "Deal Search" not in AN["Lead Create Gate"]["parameters"]["rules"]["values"][0][
        "conditions"]["conditions"][0]["leftValue"]:
    problems.append("gate guard not live")
if len(after["nodes"]) != len(ORIG["nodes"]) + 1:
    problems.append(f"node count {len(after['nodes'])} != {len(ORIG['nodes'])}+1")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
