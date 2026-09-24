#!/usr/bin/env python3
"""#26 STEP 2 — port the WF-1 alert-delivery registry from staticData to the atomic claims table.

Migration already done and verified per key (53/53). This is the cutover.

SHAPE
  M7 Build -> M7 Alert Key -> M7 DT Alert Get -> M7 Alert Gate -> (unchanged onward)
  M7 Critical Slack -> M7 IF Alert Delivered -> M7 DT Alert Claim      (claim AFTER delivery)

WHAT IS PRESERVED, deliberately:
  * STABLE KEY (2026-08-31): P<person>|<campaign>, falling back to K<provider identity>, never the
    lead id - archiving a lead must not reset suppression (Person-b093030e).
  * legacy L-form keys are still honoured on READ, never written back.
  * campaign-origin gate and its NOWHERE ruling, untouched.
  * claim-after-delivery: a failed Slack post must not burn the lead's only alert.
  * staticData registry is LEFT IN PLACE as the rollback. It simply stops being read or written.

THE DANGEROUS FAILURE, guarded explicitly: n8n's dataTable error shape is non-uniform - some ops
return {error:...}, others ECHO THE ORIGINAL INPUT ITEM with no marker. The echoed item carries
claim_key, so a naive "did I get a row back" check would read an outage as "already delivered" and
SILENCE a real first reply. The gate therefore checks POSITIVELY for the success shape
(family === 'wf1_alert' AND claimed_at present); anything else is treated as not-found and alerts.
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
TID = "euyostwJYfJefItC"
TEAM = "C07LTD8UT70"

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
if "M7 Alert Key" in N:
    sys.exit("port already applied")

GATE_JS = N["M7 Alert Gate"]["parameters"]["jsCode"]

# ---------- 1. M7 Alert Key : key computation lifted verbatim out of the gate
KEY_JS = r"""
// Key computation, lifted verbatim from M7 Alert Gate so the dataTable lookup can run BEFORE the
// decision. Nothing about the key changed - see STABLE KEY (Nik, 2026-08-31): the key must not
// depend on whether the lead is visible, because archiving a lead must never reset suppression.
const b = $json;                                  // M7 Build output
const n = $('Normalize').item.json;
const camp = String((n.campaign && (n.campaign.id ?? n.campaign.name)) ?? 'nocamp');
const li = (n.lead && (n.lead.member_id || n.lead.public_id || n.lead.li_url)) || null;
const who = b.person_id ? ('P' + b.person_id)
          : (li ? ('K' + String(li).toLowerCase()) : null);
const key = who ? (who + '|' + camp) : null;
// legacy lead-keyed entries are still honoured on READ; never written back.
const legacyKey = b.lead_id ? ('L' + b.lead_id + '|' + camp) : null;
const __manual_thread = !(n.campaign && (n.campaign.id ?? n.campaign.name));
// the lookup needs a value even when there is no key, or the dataTable node errors on an empty
// filter and we lose the distinction between "no identity" and "table unavailable".
return [{ json: { ...b, __alert_key: key, __legacy_key: legacyKey, __manual_thread,
                  __lookup_key: key || '__wf1_no_key__',
                  __lookup_legacy: legacyKey || '__wf1_no_key__' } }];
"""

# ---------- 2. the gate, rewritten to decide from the table
NEW_GATE = r"""
// W1.0.18 — the delivery registry now lives in the ATOMIC claims dataTable, not staticData.
// WHY: $getWorkflowStaticData persists the WHOLE object at execution end, so two executions in the
// same second each load the same state and the last write wins. Proven on 2026-09-01 20:50:27:
// three WF-1 executions in one second, two delivered alerts, registry went 47 -> 48 instead of 49,
// and Person-58accf5a's key was lost - she was announced again 27 hours later as a 'first_alert'.
// HeyReach fans several events for one message into the same second: 28 such groups, max 5, and 54
// true overlaps across the retained window. This is routine traffic, not an edge case.
//
// PRESERVED FROM THE staticData VERSION, all deliberate:
//   * STABLE KEY (2026-08-31) - person-keyed, never lead-keyed; archiving a lead must not reset
//     suppression (Person-b093030e).
//   * legacy 'L' entries honoured on read, never written back.
//   * the campaign-origin gate and its NOWHERE ruling (2026-08-28).
//   * claiming happens AFTER delivery, in M7 DT Alert Claim - never at decision time.
const b = $('M7 Alert Key').item.json;
const keyRow = $json;

// THE SUCCESS SHAPE MUST BE CHECKED POSITIVELY. n8n's dataTable error shape is non-uniform: some
// ops return {error:...}, others ECHO THE INPUT ITEM unchanged. The echoed item carries claim_key,
// so "did a row come back" would read an outage as 'already delivered' and silence a real first
// reply. A hit is only a hit if it looks like a stored row.
const isRow = !!(keyRow && keyRow.family === 'wf1_alert' && keyRow.claimed_at);
const hitKey = isRow ? String(keyRow.claim_key || '') : '';
const matchedCurrent = isRow && hitKey === b.__alert_key;
const matchedLegacy = isRow && !!b.__legacy_key && hitKey === b.__legacy_key;
const lookupBroken = !!(keyRow && (keyRow.error || keyRow.__error)) ||
                     (!!keyRow && keyRow.claim_key !== undefined && !isRow);

let should, reason;
if (b.__manual_thread) {
  should = false; reason = 'manual_conversation';
} else if (!b.__alert_key) {
  should = true; reason = 'no_identity';
} else if (matchedCurrent || matchedLegacy) {
  should = false;
  reason = matchedCurrent ? 'already_delivered' : 'already_delivered_legacy_lead_key';
} else if (lookupBroken) {
  // 9b.0f: alert gates fail OPEN. A duplicate is noise; a missed first reply is lost revenue.
  should = true; reason = 'dt_unavailable_fail_open';
} else {
  should = true; reason = 'first_alert';
}
return [{ json: { ...b, __alert_key: b.__alert_key, __should_alert: should,
                  __manual_thread: b.__manual_thread, __alert_reason: reason,
                  __registry_backend: 'dataTable', __dt_hit: isRow } }];
"""

GX, GY = N["M7 Alert Gate"]["position"]
CSX, CSY = N["M7 Critical Slack"]["position"]
DTCRED = None
for n in wf["nodes"]:
    if n["type"].endswith("dataTable"):
        DTCRED = n.get("credentials")
        break

new_nodes = [
    {"parameters": {"jsCode": KEY_JS}, "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [GX - 220, GY + 120], "id": "m7-alertkey", "name": "M7 Alert Key"},
    {"parameters": {"resource": "row", "operation": "get",
                    "dataTableId": {"__rl": True, "mode": "id", "value": TID},
                    "matchType": "anyCondition",
                    "filters": {"conditions": [
                        {"keyName": "claim_key", "condition": "eq",
                         "keyValue": "={{ $json.__lookup_key }}"},
                        {"keyName": "claim_key", "condition": "eq",
                         "keyValue": "={{ $json.__lookup_legacy }}"}]},
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
     "position": [GX - 110, GY + 120], "id": "m7-dtget", "name": "M7 DT Alert Get",
     "alwaysOutputData": True, "onError": "continueRegularOutput"},
    {"parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "combinator": "and",
        "conditions": [{"id": "m7-dlv",
                        "leftValue": "={{ $json.ok === true && $json.channel === '" + TEAM + "' }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}]}, "options": {}},
     "type": "n8n-nodes-base.if", "typeVersion": 2,
     "position": [CSX + 120, CSY - 130], "id": "m7-ifdlv", "name": "M7 IF Alert Delivered"},
    {"parameters": {"resource": "row", "operation": "upsert",
                    "dataTableId": {"__rl": True, "mode": "id", "value": TID},
                    "matchType": "allConditions",
                    "filters": {"conditions": [
                        {"keyName": "claim_key", "condition": "eq",
                         "keyValue": "={{ $('M7 Alert Key').item.json.__alert_key }}"}]},
                    "columns": {"mappingMode": "defineBelow", "value": {
                        "claim_key": "={{ $('M7 Alert Key').item.json.__alert_key }}",
                        "family": "wf1_alert",
                        "workflow": "WF-1",
                        "event_time": "={{ $('Normalize').item.json.ts }}",
                        "claimed_at": "={{ new Date().toISOString() }}",
                        "evidence": "={{ 'exec:' + $execution.id + ' alert-delivered' }}"}},
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
     "position": [CSX + 240, CSY - 130], "id": "m7-dtclaim", "name": "M7 DT Alert Claim",
     "onError": "continueRegularOutput"},
]
for nd in new_nodes:
    if nd["type"].endswith("dataTable") and DTCRED:
        nd["credentials"] = DTCRED
wf["nodes"].extend(new_nodes)
N.update({x["name"]: x for x in new_nodes})
N["M7 Alert Gate"]["parameters"]["jsCode"] = NEW_GATE

# ---------- 3. strip the staticData write out of M7 Labels Compute
lc = N["M7 Labels Compute"]["parameters"]["jsCode"]
start = lc.find("// Records alert DELIVERY")
end = lc.find("return __items;")
if start == -1 or end == -1 or start > end:
    sys.exit("M7 Labels Compute registry block not located - refusing to patch blind")
REPLACE = ("// The delivery registry moved to the atomic claims dataTable (W1.0.18). The claim is\n"
           "// written by `M7 DT Alert Claim`, gated on the same ok===true && channel===TEAM test\n"
           "// that used to live here. Nothing writes staticData from this node any more; the old\n"
           "// __alerted_v1 object is left untouched as the rollback copy.\n\n")
N["M7 Labels Compute"]["parameters"]["jsCode"] = lc[:start] + REPLACE + lc[end:]

# ---------- 4. wiring
C["M7 Build"] = {"main": [[{"node": "M7 Alert Key", "type": "main", "index": 0}]]}
C["M7 Alert Key"] = {"main": [[{"node": "M7 DT Alert Get", "type": "main", "index": 0}]]}
C["M7 DT Alert Get"] = {"main": [[{"node": "M7 Alert Gate", "type": "main", "index": 0}]]}
cs = C.get("M7 Critical Slack", {}).get("main", [[]])
if not cs:
    cs = [[]]
if not any(c.get("node") == "M7 IF Alert Delivered" for c in cs[0]):
    cs[0].append({"node": "M7 IF Alert Delivered", "type": "main", "index": 0})
C["M7 Critical Slack"] = {"main": cs}
C["M7 IF Alert Delivered"] = {"main": [[{"node": "M7 DT Alert Claim", "type": "main",
                                         "index": 0}], []]}

print(f"nodes added: {[n['name'] for n in new_nodes]}")
print("gate rewritten; staticData write removed from M7 Labels Compute")

# ---------------------------------------------------------------- statics
print("\n--- statics ---")
ok = True


def run(js, harness, pick):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(" + pick + "));\n"
    tmp = os.path.join(HERE, "_p26.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


def H(dtrow, akey="P85942|572715", legacy="L999|572715", manual=False):
    b = {"person_id": 85942, "lead_id": "999", "__alert_key": akey, "__legacy_key": legacy,
         "__manual_thread": manual}
    return f"""
const B = {json.dumps(b)};
const $json = {json.dumps(dtrow)};
const $ = (nm) => {{
  if (nm === 'M7 Alert Key') return {{ item: {{ json: B }} }};
  if (nm === 'Normalize') return {{ item: {{ json: {{ ts: '2026-09-03T00:00:00Z' }} }} }};
  throw new Error('absent ' + nm);
}};
"""


ROW = {"claim_key": "P85942|572715", "family": "wf1_alert",
       "claimed_at": "2026-09-02T23:55:27.155Z", "workflow": "WF-1"}
LEG = {"claim_key": "L999|572715", "family": "wf1_alert",
       "claimed_at": "2026-08-20T00:00:00.000Z", "workflow": "WF-1"}
CASES = [
    ("stored row for the current key -> already_delivered", H(ROW), False, "already_delivered"),
    ("stored row for the LEGACY key -> honoured, not re-announced",
     H(LEG), False, "already_delivered_legacy_lead_key"),
    ("no row -> first_alert", H({}), True, "first_alert"),
    ("dataTable ECHOES THE INPUT (non-uniform error shape) -> must NOT read as delivered",
     H({"claim_key": "P85942|572715", "__alert_key": "P85942|572715", "person_id": 85942}),
     True, "dt_unavailable_fail_open"),
    ("dataTable returns an error object -> fail OPEN",
     H({"error": "table unavailable"}), True, "dt_unavailable_fail_open"),
    ("manual conversation -> silence (regression)", H({}, manual=True), False,
     "manual_conversation"),
    ("no identity -> fail open (regression)", H({}, akey=None, legacy=None), True, "no_identity"),
]
for label, h, want_should, want_reason in CASES:
    got, err = run(NEW_GATE, h, "{s: OUT[0].json.__should_alert, r: OUT[0].json.__alert_reason,"
                                " hit: OUT[0].json.__dt_hit}")
    if err:
        print(f"  [FAIL] {label}\n         {err}")
        ok = False
        continue
    good = got["s"] is want_should and got["r"] == want_reason
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         should={got['s']} reason={got['r']!r} dt_hit={got['hit']}")

# the key node must still produce the STABLE key
kh = """
const B = { person_id: 85942, lead_id: 'abc' };
const $json = B;
const $ = (nm) => { if (nm === 'Normalize') return { item: { json: {
  campaign: { id: 572715 }, lead: { member_id: null } } } };
  throw new Error('absent ' + nm); };
"""
got, err = run(KEY_JS, kh, "{k: OUT[0].json.__alert_key, l: OUT[0].json.__legacy_key,"
                           " lk: OUT[0].json.__lookup_key}")
good = (not err and got["k"] == "P85942|572715" and got["l"] == "Labc|572715")
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] M7 Alert Key preserves the STABLE key form  "
      f"{got if not err else err}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_p26_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in [x["name"] for x in new_nodes]:
    if nm not in AN:
        problems.append(f"{nm} missing")
if "getWorkflowStaticData" in AN["M7 Alert Gate"]["parameters"]["jsCode"]:
    problems.append("gate still reads staticData")
if "__alerted_v1" in AN["M7 Labels Compute"]["parameters"]["jsCode"]:
    problems.append("Labels Compute still writes staticData")
if AN.get("M7 DT Alert Get", {}).get("onError") != "continueRegularOutput":
    problems.append("DT Get is blocking")
bo = [c.get("node") for g in (AC.get("M7 Build") or {}).get("main", []) for c in (g or [])]
if bo != ["M7 Alert Key"]:
    problems.append(f"M7 Build rewire wrong: {bo}")
so = [c.get("node") for g in (AC.get("M7 Critical Slack") or {}).get("main", []) for c in (g or [])]
if "M7 IF Alert Delivered" not in so or "M7 IF Patch" not in so:
    problems.append(f"Critical Slack fan-out wrong: {so}")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
print(f"  Critical Slack -> {so}")
