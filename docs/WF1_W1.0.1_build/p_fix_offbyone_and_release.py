#!/usr/bin/env python3
"""Three fixes in one window, plus three key releases. Authorized by Nik 2026-08-11.

1. OFF-BY-ONE (mine). `completeExpression` was `$pageCount >= (cands.length - 1)`. n8n evaluates it
   AFTER each response with $pageCount already incremented, so it stops one candidate short. Live
   proof, exec 15239: 4 candidates [84885,84886,84887,85506], only 3 requests, and 85506 - the one
   holding the fixture lead - was never asked. It only bites DUPLICATES, which is precisely the case
   B27 exists for. Fix: `>= cands.length`. Safe either way: the worst case is one extra request with
   person_id=-1, which matches nothing.

   Worth stating: `__leads_page_saturated` came back TRUE (3 read < 4 candidates). The coverage flag
   caught my bug. It reached Nik only as a no-lead warning because that flag still has no consumer
   (section 9b.0b) - the sensor worked, the wiring to a human did not.

2. REPLY CRM DONE CLAIM GUARD (also mine). P0-1b claimed exec 15239 even though __no_lead was true -
   person-side writes only, no lead work. "Reached a success terminal" and "did the work" diverged.
   A half-processed event must stay replayable, so the claim now requires __no_lead === false. If
   Lead Resolve cannot be read at all, it does NOT claim: staying replayable is recoverable,
   claiming a half-done event is not.

3. KEY RELEASES (staticData, PUT-carried):
   * wf2_seen - fixture REPLIED|3686187|4306240392|1786452347000 (the live specimen of bug 1)
   * wf2_seen - Marine REPLIED|3686184|4214180591|1786375820000 (auditor assertion 4: dedupe TTL and
     WF-2R lookback are both 48h, so they expire together and the event NEVER self-recovers)
   * __alert_delivered - '84885'. Checked for other dupe-set ghosts as asked: the registry holds
     exactly ONE entry, so this clears it completely.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
LISTS = ["R Lead List", "Lead List", "B Lead List", "U Lead List"]
DROP_SEEN = ["REPLIED|3686187|4306240392|1786452347000",
             "REPLIED|3686184|4214180591|1786375820000"]
DROP_ALERT = ["84885"]

OLD_CLAIM = """// P0-1b claim-after-success: reaching this node means the branch's work completed.
try {
  const __k = $('Dedupe').item.json.__dedupe_key;
  if (__k) {
    const __sd = $getWorkflowStaticData('global');
    (__sd.wf2_seen = __sd.wf2_seen || {})[__k] = Math.floor(Date.now() / 1000);
  }
} catch (e) { /* not on this branch */ }"""

NEW_CLAIM = """// P0-1b claim-after-success, WITH the no-lead guard added 2026-08-11.
// Reaching this node is not the same as having done the work: exec 15239 arrived here with
// __no_lead true (person-side writes only, no lead resolved) and claimed anyway, making a
// half-processed reply unreplayable for 48h. Claim only on a resolved lead.
// If Lead Resolve cannot be read at all we do NOT claim: an unnecessary replay is recoverable
// (dedupe and existence checks absorb it), a wrongly-claimed event is not.
try {
  const __lr = (() => { try { return $('Lead Resolve').item.json; } catch (e) { return null; } })();
  const __resolved = !!(__lr && __lr.__no_lead === false);
  const __k = $('Dedupe').item.json.__dedupe_key;
  if (__k && __resolved) {
    const __sd = $getWorkflowStaticData('global');
    (__sd.wf2_seen = __sd.wf2_seen || {})[__k] = Math.floor(Date.now() / 1000);
  }
} catch (e) { /* not on this branch */ }"""


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            print(f"   HTTP {e.code} on {method} {path[:52]} - retry {attempt + 1}", flush=True)
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


def run_case(js, label, lead_resolve, want):
    harness = f"""
const __sd = {{ wf2_seen: {{}} }};
const $getWorkflowStaticData = () => __sd;
const $input = {{ all: () => [{{ json: {{}} }}] }};
const $json = {{}};
const $ = (nm) => {{
  if (nm === 'Dedupe') return {{ item: {{ json: {{ __dedupe_key: 'KEY1' }} }} }};
  if (nm === 'Lead Resolve') {{
    const lr = {json.dumps(lead_resolve)};
    if (lr === null) throw new Error('Lead Resolve unavailable');
    return {{ item: {{ json: lr }} }};
  }}
  throw new Error('absent: ' + nm);
}};
const __out = (() => {{
{js}
}})();
console.log(JSON.stringify({{
  claimed: Object.prototype.hasOwnProperty.call(__sd.wf2_seen, 'KEY1'),
  out: JSON.stringify(__out)
}}));
"""
    tmp = os.path.join(HERE, "_offby_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-200:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return not bad


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

# ---- 1. off-by-one
fixed = []
for nm in LISTS:
    pg = ((N[nm]["parameters"].get("options") or {}).get("pagination") or {}).get("pagination")
    if not pg:
        raise SystemExit(f"{nm}: no pagination")
    ce = pg["completeExpression"]
    if ".length - 1) }}" in ce:
        pg["completeExpression"] = ce.replace(".length - 1) }}", ".length) }}")
        fixed.append(nm)
    elif ".length) }}" not in ce:
        raise SystemExit(f"{nm}: unrecognised completeExpression, refusing to edit blind:\n  {ce}")

# ---- 2. claim guard
rcd = N["Reply CRM Done"]["parameters"]["jsCode"]
guard_needed = "__no_lead === false" not in rcd
if guard_needed:
    if OLD_CLAIM not in rcd:
        raise SystemExit("Reply CRM Done: claim anchor missing, refusing to patch blind")
    new_rcd = rcd.replace(OLD_CLAIM, NEW_CLAIM)
else:
    new_rcd = rcd

print(f"\n--- statics: EXECUTING the patched Reply CRM Done body ---")
ok = True
ok = run_case(new_rcd, "reply RESOLVED a lead -> claims",
              {"__no_lead": False, "__lead_id": "L1"},
              {"claimed": True, "out": '[{"json":{"done":true}}]'}) and ok
ok = run_case(new_rcd, "reply resolved NO lead -> key ABSENT, stays replayable (exec 15239)",
              {"__no_lead": True, "__lead_id": None},
              {"claimed": False, "out": '[{"json":{"done":true}}]'}) and ok
ok = run_case(new_rcd, "Lead Resolve unreadable -> conservative, does NOT claim",
              None, {"claimed": False, "out": '[{"json":{"done":true}}]'}) and ok
ok = run_case(new_rcd, "__no_lead missing entirely -> does NOT claim",
              {"__lead_id": "L1"}, {"claimed": False}) and ok
if not ok:
    sys.exit(1)

sd = copy.deepcopy((wf.get("staticData") or {}).get("global") or {})
seen, alert = sd.get("wf2_seen") or {}, sd.get("__alert_delivered") or {}
print("\n--- planned ---")
print(f"  - completeExpression '>= length' on: {fixed or '(already fixed)'}")
print(f"  - Reply CRM Done no-lead guard: {'ADD' if guard_needed else '(already present)'}")
for k in DROP_SEEN:
    print(f"  - wf2_seen release: {k}   present={k in seen}")
for k in DROP_ALERT:
    print(f"  - __alert_delivered release: {k!r}   present={k in alert}")
print(f"    (__alert_delivered holds {len(alert)} entr(y/ies) total: {list(alert.keys())})")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_offbyone_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))

N["Reply CRM Done"]["parameters"]["jsCode"] = new_rcd
# Re-read staticData immediately before the PUT: WF-2 is live and writes these registries itself,
# so a stale copy would silently roll back any claim made in the meantime.
fresh = ((n8n(f"/api/v1/workflows/{WF2}").get("staticData") or {}).get("global") or {})
fseen = dict(fresh.get("wf2_seen") or {})
falert = dict(fresh.get("__alert_delivered") or {})
removed_seen = [k for k in DROP_SEEN if fseen.pop(k, None) is not None]
removed_alert = [k for k in DROP_ALERT if falert.pop(k, None) is not None]
body = put_body(wf)
body["staticData"] = {"global": {**fresh, "wf2_seen": fseen, "__alert_delivered": falert}}
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
print(f"  releasing from wf2_seen: {removed_seen}")
print(f"  releasing from __alert_delivered: {removed_alert}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", body)

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
asd = (after.get("staticData") or {}).get("global") or {}
aseen, aalert = asd.get("wf2_seen") or {}, asd.get("__alert_delivered") or {}
problems = []
for nm in LISTS:
    ce = (((an[nm]["parameters"].get("options") or {}).get("pagination") or {})
          .get("pagination") or {}).get("completeExpression", "")
    if ".length - 1)" in ce:
        problems.append(f"{nm}: still off-by-one")
    if ".length)" not in ce:
        problems.append(f"{nm}: completeExpression unexpected")
if "__no_lead === false" not in an["Reply CRM Done"]["parameters"]["jsCode"]:
    problems.append("Reply CRM Done guard missing")
for k in DROP_SEEN:
    if k in aseen:
        problems.append(f"wf2_seen still holds {k}")
for k in DROP_ALERT:
    if k in aalert:
        problems.append(f"__alert_delivered still holds {k}")
if after.get("active") is not wf.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
print(f"  wf2_seen={len(aseen)} entries, __alert_delivered={len(aalert)} entries")
sys.exit(1 if problems else 0)
