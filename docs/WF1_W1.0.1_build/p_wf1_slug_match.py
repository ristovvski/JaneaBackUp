#!/usr/bin/env python3
"""WF-1 person-match by LinkedIn SLUG instead of a verbatim URL, + honest warn wording.

THE BUG (Person-9979a87c, exec 16703): every `Person Search URL` node sends
`term = lead.url, exact_match=true`. HeyReach sends 'https://www.linkedin.com/in/pii-7a798b9a';
Pipedrive stores 'https://linkedin.com/in/pii-7a798b9a'. exact_match on two strings differing by
'www.' returns 0 items, and the alert then asserted 'not in Pipedrive' about a person who exists
(85517, with a lead and two human activities).

THE FIX mirrors W1.0.16's member fallback, which already got this right: search by a normalised KEY
and then VERIFY the hit against the person's own field, rather than trusting the search.
  term        -> the slug ('philipcootey'), exact_match=false
  IF URL Found -> not `items.length > 0`, but "some returned person carries a LinkedIn value whose
                  slug equals ours". Widening the search without tightening the check would trade a
                  false negative for a false positive.
Normalisation subsumes www/no-www, http/https, trailing slash, /pub/ and percent-encoding.

Note persons/search returns custom_fields as a FLAT ARRAY with no field keys - the same shape
W1.0.16 had to handle - so verification scans values, it cannot look up by field id.

ALSO (Nik, item 4): 'not in Pipedrive' becomes 'no match found (person may exist under a different
URL/email form)'. The alert asserted an absence it could not know - same family as the WF-ERR LOST
wording.
"""
import argparse, copy, json, os, re, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"

SLUG_JS = (
    "const __slugOf = (u) => { const s = String(u == null ? '' : u).trim().toLowerCase(); "
    "const m = s.match(/linkedin\\.com\\/(?:in|pub)\\/([^\\/?#\\s]+)/); "
    "if (m) { try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; } } "
    "const bare = s.replace(/^\\/+|\\/+$/g, ''); "
    "return (bare && bare.indexOf('/') === -1 && bare.indexOf('.') === -1 && bare.length >= 3) "
    "? bare : ''; };"
)
OURS_JS = ("const __ours = (() => { const l = $('Normalize').item.json.lead || {}; "
           "return __slugOf(l.slug) || __slugOf(l.url) || __slugOf(l.profile_url) || ''; })();")

TERM = ("={{ (() => { " + SLUG_JS + " " + OURS_JS +
        " return __ours || '__wf1_no_slug__'; })() }}")

VERIFY = ("={{ (() => { " + SLUG_JS + " " + OURS_JS +
          " if (!__ours) return false;"
          " const items = ($json.data && $json.data.items) || [];"
          " const holds = (x) => { const arr = ((x || {}).item || {}).custom_fields;"
          "   if (!Array.isArray(arr)) return false;"
          "   for (const v of arr) { if (v === null || v === undefined) continue;"
          "     for (const part of String(v).split(',')) {"
          "       if (__slugOf(part) === __ours) return true; } }"
          "   return false; };"
          " return items.some(holds); })() }}")

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n_wf = None


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if attempt < 4:
            time.sleep(8)
            return n8n(path, method, body, attempt + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF1}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

search_nodes = [n for n in wf["nodes"] if n["name"].endswith("Person Search URL")]
if_nodes = [n for n in wf["nodes"] if n["name"].endswith("IF URL Found")]
print(f"Person Search URL nodes : {[n['name'] for n in search_nodes]}")
print(f"IF URL Found nodes      : {[n['name'] for n in if_nodes]}")

# every search node must have a verifying IF downstream, or we would widen a search and never
# tighten it. Map via connections rather than assuming the name pairing.
conns = wf.get("connections") or {}
unpaired = []
for s in search_nodes:
    downstream = set()
    for grp in (conns.get(s["name"], {}) or {}).get("main", []) or []:
        for c in grp or []:
            downstream.add(c.get("node"))
    if not (downstream & {n["name"] for n in if_nodes}):
        unpaired.append((s["name"], sorted(downstream)))
if unpaired:
    print("\nSEARCH NODES WITH NO 'IF URL Found' DOWNSTREAM:")
    for nm, d in unpaired:
        print(f"   {nm} -> {d}")
    sys.exit("refusing to widen a search whose result is not verified")
print("every search node has a verifying IF downstream: OK")

# ---------------------------------------------------------------- statics
print("\n--- statics: run the verification expression body ---")


def run_verify(ours_url, ours_slug, stored_values):
    body = VERIFY[5:-4]  # strip '={{ ' and ' }}'
    src = f"""
const NORM = {{ lead: {{ url: {json.dumps(ours_url)}, slug: {json.dumps(ours_slug)} }} }};
const $ = (nm) => ({{ item: {{ json: NORM }} }});
const $json = {{ data: {{ items: {json.dumps([{"item": {"id": 1, "custom_fields": stored_values}}])} }} }};
const OUT = ({body});
console.log(JSON.stringify({{ v: OUT }}));
"""
    tmp = os.path.join(HERE, "_slug.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1])["v"], None


CASES = [
    ("THE COOTEY PAIR: www-form in, no-www stored -> MUST match (this is the live bug)",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["https://linkedin.com/in/pii-7a798b9a"], True),
    ("CONTROL: a DIFFERENT slug must still MISS (no false positives)",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["https://linkedin.com/in/pii-9107e194"], False),
    ("CONTROL: same-name different person, /in/philipcootey2 -> MISS",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["https://www.linkedin.com/in/pii-029717c8"], False),
    ("trailing slash + http stored -> match",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["http://linkedin.com/in/pii-7a798b9a/"], True),
    ("/pub/ form stored -> match",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["https://www.linkedin.com/pub/philipcootey"], True),
    ("comma-joined multi-value field -> match",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["something, https://linkedin.com/in/pii-7a798b9a"], True),
    ("no slug on our side -> MISS, never match-all",
     "", "", ["https://linkedin.com/in/pii-7a798b9a"], False),
    ("person carries no linkedin value at all -> MISS",
     "https://www.linkedin.com/in/pii-7a798b9a", "philipcootey",
     ["Greater Boston", "Babel Street"], False),
]
ok = True
for label, url, slug, stored, want in CASES:
    got, err = run_verify(url, slug, stored)
    if err:
        print(f"  [FAIL] {label}\n         {err}")
        ok = False
        continue
    good = got is want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         verified={got} (want {want})")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")

# ---------------------------------------------------------------- warn wording
warn_changed = []
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters"), ensure_ascii=False)
    if "not in Pipedrive" in blob:
        new = blob.replace(
            "not in Pipedrive",
            "no match found (person may exist under a different URL/email form)")
        n["parameters"] = json.loads(new)
        warn_changed.append(n["name"])
print(f"\nwarn wording updated in: {warn_changed or 'NONE FOUND'}")

# ---------------------------------------------------------------- apply
for s in search_nodes:
    params = s["parameters"]
    for q in params["queryParameters"]["parameters"]:
        if q["name"] == "term":
            q["value"] = TERM
        elif q["name"] == "exact_match":
            q["value"] = "false"
for f in if_nodes:
    f["parameters"]["conditions"]["conditions"][0]["leftValue"] = VERIFY
    f["parameters"]["conditions"]["conditions"][0]["rightValue"] = True
    f["parameters"]["conditions"]["conditions"][0]["operator"] = {
        "type": "boolean", "operation": "true", "singleValue": True}

print(f"\nplanned: {len(search_nodes)} search nodes -> slug term + exact_match=false")
print(f"         {len(if_nodes)} IF nodes -> slug verification against custom_fields")
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_slug_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
for s in search_nodes:
    qs = {q["name"]: q["value"] for q in
          AN[s["name"]]["parameters"]["queryParameters"]["parameters"]}
    if "__wf1_no_slug__" not in str(qs.get("term")):
        problems.append(f"{s['name']} term not live")
    if str(qs.get("exact_match")) != "false":
        problems.append(f"{s['name']} exact_match still {qs.get('exact_match')}")
for f in if_nodes:
    if "__slugOf" not in str(AN[f["name"]]["parameters"]["conditions"]["conditions"][0]["leftValue"]):
        problems.append(f"{f['name']} verification not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
