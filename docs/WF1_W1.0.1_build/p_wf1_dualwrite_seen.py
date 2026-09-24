#!/usr/bin/env python3
"""DUAL-WRITE phase 1: WF-1's `seen` store also writes to wf_claims. staticData stays AUTHORITATIVE.

Scope filter (section 9b.0g): exactly one workflow id, asserted. No discovery.

WHAT THIS IS NOT: it is not the P0-1b port. `Dedupe`'s logic is UNCHANGED - it still claims in
staticData at decision time, still returns [] on a duplicate. We are only ADDING an observation
write so tomorrow's comparison has data. Changing behaviour and measuring it in the same step would
make the comparison uninterpretable, which is the whole point of a dual-write phase.

SHAPE: a NON-BLOCKING TEE off `Dedupe`, the pattern WF-1 already uses for `Event Marker Warn`
(`Normalize` -> `IF Event Marker Bad` -> warn). The tee dead-ends, so the dataTable node's output
never reaches the main spine - which matters because an upsert node emits the ROW it wrote, not the
event. Wiring it in-line would feed `Normalize` a table row instead of a webhook body.

FAIL-OPEN BY CONSTRUCTION, not by vigilance:
  * separate branch  -> `Normalize` runs regardless of what the tee does
  * onError: continueRegularOutput -> a table error cannot fail the execution
  * staticData authoritative -> if every table write failed, WF-1 behaves exactly as today

SCOPE NOTE - only the `seen` family tonight. The alert family (`__alerted_v1`) is deferred: it fires
~3 times in two days, so a night of observation yields no comparable data, and its claim is
conditional (ok:true AND channel === team) which needs more than a tee. It rides with tomorrow's
port, where behaviour changes anyway.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"          # the ONLY id this script may touch
TABLE = "euyostwJYfJefItC"
TEE = "DT Claim Seen"

OLD_RET = "return [{ json: body }];"
NEW_RET = """// DUAL-WRITE (observation phase): publish the claim key and the event's own instant so the
// tee can write them to wf_claims. staticData above is UNCHANGED and remains authoritative.
// `event_time` is the PROVIDER's timestamp, never an execution clock - execution timestamps are
// nullable on failure and are the wrong clock for any lookback or rotation logic.
return [{ json: { ...body,
  __claim_key: 'S|' + key,
  __event_time: body.timestamp || null,
  __claimed_at: new Date(now).toISOString() } }];"""


def n8n(path, q=None, method="GET", body=None, attempt=0):
    import time, urllib.parse
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


def run_case(js, label, body, seen0, want):
    harness = f"""
const __sd = {{ seen: {json.dumps(seen0)} }};
const $getWorkflowStaticData = () => __sd;
const BODY = {json.dumps(body)};
const $ = (nm) => {{ if (nm === 'Webhook') return {{ item: {{ json: {{ body: BODY }} }} }};
                     throw new Error('absent ' + nm); }};
const __out = (() => {{
{js}
}})();
const first = (__out && __out[0]) ? __out[0].json : null;
console.log(JSON.stringify({{
  emitted: Array.isArray(__out) ? __out.length : -1,
  claim_key: first ? (first.__claim_key ?? null) : null,
  event_time: first ? (first.__event_time ?? null) : null,
  has_original: !!(first && first.event_type !== undefined),
  seen_written: Object.keys(__sd.seen).length
}}));
"""
    tmp = os.path.join(HERE, "_dw_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-220:]}")
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

wf = n8n(f"/api/v1/workflows/{WF1}")
if wf.get("id") != WF1:
    raise SystemExit(f"id mismatch: asked {WF1}, got {wf.get('id')}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
ded = N["Dedupe"]["parameters"]["jsCode"]
need_code = "__claim_key" not in ded
if need_code and OLD_RET not in ded:
    raise SystemExit("Dedupe: return anchor missing - refusing to patch blind")
new_ded = ded if not need_code else ded.replace(OLD_RET, NEW_RET)

print(f"WF-1 {wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")
print("\n--- statics: EXECUTING the patched Dedupe body ---")
CORR = {"correlation_id": "c-123", "event_type": "every_message_reply_received",
        "timestamp": "2026-08-13T09:15:00.000Z", "lead": {"profile_url": "https://li/in/x"}}
NOCORR = {"event_type": "message_sent", "timestamp": "2026-08-13T09:16:00.000Z",
          "lead": {"profile_url": "https://li/in/y"}, "conversation_id": "conv-9"}
NIL = {**CORR, "correlation_id": "00000000-0000-0000-0000-000000000000"}
ok = True
ok = run_case(new_ded, "fresh event -> emits claim key + provider event_time, original intact",
              CORR, {}, {"emitted": 1, "claim_key": "S|c-123",
                         "event_time": "2026-08-13T09:15:00.000Z",
                         "has_original": True, "seen_written": 1}) and ok
# NOTE: the seed must be RECENT. A first attempt seeded 1786000000000 (~Aug 8) and the test failed
# with emitted=1 - correctly, because Dedupe prunes entries older than 48h BEFORE the duplicate
# check, so a stale seed makes the event genuinely fresh. The fixture was wrong, not the code.
FRESH = int(datetime.now(timezone.utc).timestamp() * 1000) - 60_000
ok = run_case(new_ded, "DUPLICATE still short-circuits (behaviour unchanged)",
              CORR, {"c-123": FRESH}, {"emitted": 0, "seen_written": 1}) and ok
ok = run_case(new_ded, "seed older than 48h is pruned, so the event is fresh again",
              CORR, {"c-123": FRESH - 49 * 3600 * 1000}, {"emitted": 1}) and ok
ok = run_case(new_ded, "no correlation_id -> composite key, still emitted",
              NOCORR, {}, {"emitted": 1, "has_original": True,
                           "claim_key": "S|message_sent|https://li/in/y|"
                                        "2026-08-13T09:16:00.000Z|conv-9"}) and ok
ok = run_case(new_ded, "nil correlation_id -> falls back to composite (unchanged rule)",
              NIL, {}, {"emitted": 1, "has_original": True}) and ok
ok = run_case(new_ded, "staticData STILL authoritative - seen written exactly as before",
              CORR, {}, {"seen_written": 1}) and ok
if not ok:
    sys.exit(1)

tee_exists = TEE in N
print("\n--- planned ---")
print(f"  Dedupe -> emits __claim_key / __event_time  ({'ADD' if need_code else 'present'})")
print(f"  + {TEE}: non-blocking tee, dataTable upsert into {TABLE} "
      f"({'ADD' if not tee_exists else 'present'})")
print(f"  staticData: UNCHANGED and authoritative")
if not need_code and tee_exists:
    print("(already applied)")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_dualwrite_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))

N["Dedupe"]["parameters"]["jsCode"] = new_ded
if not tee_exists:
    dx, dy = (N["Dedupe"].get("position") or [0, 0])[:2]
    wf["nodes"].append({
        "parameters": {
            "resource": "row", "operation": "upsert",
            "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
            "matchType": "allConditions",
            "filters": {"conditions": [
                {"keyName": "claim_key", "condition": "eq",
                 "keyValue": "={{ $json.__claim_key }}"}]},
            "columns": {"mappingMode": "defineBelow", "value": {
                "claim_key": "={{ $json.__claim_key }}",
                "family": "wf1_seen",
                "workflow": "WF-1",
                "event_time": "={{ $json.__event_time }}",
                "claimed_at": "={{ $json.__claimed_at }}",
                "evidence": "={{ 'exec:' + $execution.id + ' dualwrite' }}"}},
            "options": {}},
        "id": "d7c1a1m0-0000-4000-8000-000000000001", "name": TEE,
        "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
        "position": [dx + 60, dy + 220],
        "onError": "continueRegularOutput", "retryOnFail": True, "maxTries": 3,
        "waitBetweenTries": 2000})
    conns = wf["connections"].setdefault("Dedupe", {}).setdefault("main", [[]])
    conns[0] = (conns[0] or []) + [{"node": TEE, "type": "main", "index": 0}]

was = wf.get("active")
d = stripped_keys(wf)
if d:
    print(f"stripping {d}")
n8n(f"/api/v1/workflows/{WF1}", None, "PUT", put_body(wf))

after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after["connections"]
problems = []
if "__claim_key" not in AN["Dedupe"]["parameters"]["jsCode"]:
    problems.append("Dedupe does not emit __claim_key")
if "sd.seen[key] = now" not in AN["Dedupe"]["parameters"]["jsCode"]:
    problems.append("staticData write was lost - dual-write must ADD, never replace")
if TEE not in AN:
    problems.append("tee node missing")
else:
    if AN[TEE].get("onError") != "continueRegularOutput":
        problems.append("tee is not fail-open")
    if not any(c["node"] == TEE for b in (AC.get("Dedupe") or {}).get("main") or []
               for c in (b or [])):
        problems.append("tee not wired off Dedupe")
if not any(c["node"] == "Normalize" for b in (AC.get("Dedupe") or {}).get("main") or []
           for c in (b or [])):
    problems.append("*** Dedupe no longer feeds Normalize - MAIN SPINE BROKEN")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]) + (0 if tee_exists else 1):
    problems.append(f"node count {len(after['nodes'])} unexpected")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
print(f"  Dedupe out: {[c['node'] for b in (AC.get('Dedupe') or {}).get('main') or [] for c in (b or [])]}")
sys.exit(1 if problems else 0)
