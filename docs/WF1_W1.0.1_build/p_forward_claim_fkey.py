#!/usr/bin/env python3
"""FORWARD-CLAIM: a separate F|<dedupe_key>, so a replay retries CRM writes but NEVER re-sends mail.

The problem this closes. The no-lead guard (deployed earlier today) correctly keeps a half-processed
reply REPLAYABLE. But a replay re-runs the whole REPLIED branch - including `SL Forward Email`. So
the guard that stops us losing events would have started us sending duplicate mail to reps, which is
precisely the defect the flip spent a day eliminating. Two different claims are needed because the
work is not one unit: the CRM writes are idempotent-ish and worth retrying, the outbound email is
not and must happen exactly once.

Shape (the auditor's): claim `F|<dedupe_key>` on forward SUCCESS, and gate the forward on its
absence. Independent of the main dedupe key, so releasing one never re-arms the other.

Implementation - no new nodes, because the graph already has the right seams:
  * `Gate SL Forward Email` already routes on `WRITE_MODE === 'live' && $json.__skip !== true`, and
    `Body SL Forward Email` computes that `__skip`. So the gate is one added disjunct there.
  * `Body Lead Labels Union` is fed DIRECTLY by `SL Forward Email` (and by the skip path, and by
    two non-forward paths), so it can carry the claim with the same try/catch idiom used in WF-1:
    on paths where the forward never ran, the node lookup throws and nothing is claimed.

FAIL-OPEN, deliberately: if the dedupe key cannot be read at all, the forward still goes. A missing
forward is a human not hearing about a reply; a duplicate forward is embarrassing but visible. And
if we cannot read the key we also cannot claim it, so a replay would forward anyway - blocking here
would buy nothing and cost the primary delivery.

Also seeds the F-key for the 12:45:47 specimen (exec 15239), which DID forward - verified on the
wire: `{"ok": true, "messageId": "<284d27db-...>", "status": "success"}` to rune@janeasystems.com.
Its main key was released for replay, so without this seed it is a canary armed to re-send tonight.
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
SPECIMEN = "REPLIED|3686187|4306240392|1786452347000"

OLD_SKIP = """return [{ json: { ...$json, __body: body,
  __skip: !body.to_emails || (!body.message_id && !body.stats_id),"""
NEW_SKIP = """// FORWARD-CLAIM (2026-08-11): the outbound email must happen EXACTLY ONCE, even though the
// event stays replayable for its CRM writes. `F|<dedupe_key>` is claimed after a successful send
// (in Body Lead Labels Union) and checked here. Separate from the main dedupe key on purpose:
// releasing one for replay must never re-arm the other.
// Fail-open: if the key cannot be read we still forward. A reply nobody hears about is worse than
// a rare duplicate - and if we cannot read the key we cannot claim it either, so blocking would
// buy nothing.
const __fkey = (() => {
  try { const k = $('Dedupe').item.json.__dedupe_key; return k ? ('F|' + k) : null; }
  catch (e) { return null; }
})();
const __already_forwarded = (() => {
  try {
    if (!__fkey) return false;
    const sd = $getWorkflowStaticData('global');
    return !!((sd.wf2_seen || {})[__fkey]);
  } catch (e) { return false; }
})();
return [{ json: { ...$json, __body: body,
  __forward_key: __fkey, __forward_already_sent: __already_forwarded,
  __skip: __already_forwarded || !body.to_emails || (!body.message_id && !body.stats_id),"""

CLAIM = """
// FORWARD-CLAIM: record that the email actually WENT. Reached from four paths - only the one
// through `SL Forward Email` may claim, and the lookup throws on the others, which is what
// distinguishes them. `ok !== true` (the node carries onError: continueRegularOutput, so it
// continues even when the send fails) must NOT claim, or a failed send becomes unrepeatable.
try {
  const __f = $('SL Forward Email').item.json;
  if (__f && __f.ok === true) {
    const __k = $('Dedupe').item.json.__dedupe_key;
    if (__k) {
      const __sd = $getWorkflowStaticData('global');
      (__sd.wf2_seen = __sd.wf2_seen || {})['F|' + __k] = Math.floor(Date.now() / 1000);
    }
  }
} catch (e) { /* forward did not run on this path */ }
"""


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
            print(f"   HTTP {e.code} on {method} {path[:50]} - retry {attempt + 1}", flush=True)
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


def node_js(js, store, mocks, extra=""):
    return f"""
const __sd = {{ wf2_seen: {json.dumps(store)} }};
const $getWorkflowStaticData = () => __sd;
const $json = {json.dumps(mocks['json'])};
const $input = {{ all: () => [{{ json: $json }}] }};
const $ = (nm) => {{
  const M = {json.dumps(mocks['nodes'])};
  if (!(nm in M)) throw new Error('absent: ' + nm);
  if (M[nm] === null) throw new Error('did not run: ' + nm);
  return {{ item: {{ json: M[nm] }} }};
}};
const __out = (() => {{
{js}
}})();
{extra}
"""


def run(js, store, mocks, label, want, extra_report=""):
    src = node_js(js, store, mocks, extra_report or
                  "console.log(JSON.stringify({ skip: __out[0].json.__skip,"
                  " fkey: __out[0].json.__forward_key,"
                  " already: __out[0].json.__forward_already_sent,"
                  " claimed: Object.keys(__sd.wf2_seen).filter(k => k.indexOf('F|') === 0) }));")
    tmp = os.path.join(HERE, "_fwd_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-220:]}")
        return False, {}
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return (not bad), got


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

bfe = N["Body SL Forward Email"]["parameters"]["jsCode"]
blu = N["Body Lead Labels Union"]["parameters"]["jsCode"]
need_gate = "__forward_already_sent" not in bfe
need_claim = "'F|' + __k" not in blu
if need_gate and OLD_SKIP not in bfe:
    raise SystemExit("Body SL Forward Email: anchor missing, refusing to patch blind")
new_bfe = bfe.replace(OLD_SKIP, NEW_SKIP) if need_gate else bfe
new_blu = (("const __items = (() => {\n" + blu + "\n})();\n" + CLAIM + "\nreturn __items;")
           if need_claim else blu)

DK = "REPLIED|C|L|T"
CFG = {"fields": {}, "labels": {"cold": "K", "connected": "C2", "responded": "R"}}
BODY_JSON = {"__forward_to": "rune@janeasystems.com", "__message_id": "M1", "__stats_id": "S1",
             "__history": [], "__lead_id": "L1", "__lead_labels": []}

print("\n--- statics: gate (Body SL Forward Email) ---")
ok = True
o1, g1 = run(new_bfe, {}, {"json": BODY_JSON,
                           "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                                     "Dedupe": {"__dedupe_key": DK}, "Apply Enrich": None}},
             "first run, F-key absent -> FORWARDS",
             {"skip": False, "fkey": "F|" + DK, "already": False})
ok = o1 and ok
o2, _ = run(new_bfe, {"F|" + DK: 1786400000},
            {"json": BODY_JSON, "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                                          "Dedupe": {"__dedupe_key": DK}, "Apply Enrich": None}},
            "REPLAY, F-key present -> SKIPS (zero second forward)",
            {"skip": True, "already": True})
ok = o2 and ok
o3, _ = run(new_bfe, {"F|" + DK: 1786400000},
            {"json": {**BODY_JSON, "__forward_to": ""},
             "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                       "Dedupe": {"__dedupe_key": DK}, "Apply Enrich": None}},
            "existing skip reasons still apply (no to_emails)", {"skip": True})
ok = o3 and ok
o4, _ = run(new_bfe, {}, {"json": BODY_JSON,
                          "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                                    "Dedupe": None, "Apply Enrich": None}},
            "Dedupe unreadable -> FAIL-OPEN, still forwards",
            {"skip": False, "fkey": None, "already": False})
ok = o4 and ok

print("\n--- statics: claim (Body Lead Labels Union) ---")
REPORT = ("console.log(JSON.stringify({ claimed:"
          " Object.keys(__sd.wf2_seen).filter(k => k.indexOf('F|') === 0),"
          " out_len: __out.length, lead: __out[0].json.__lead_id }));")
base_nodes = {"CONFIG": CFG, "Normalize": {"reply": {}}, "Apply Enrich": None,
              "Mark DNC": None, "U Mark DNC": None, "Merge Reply Ctx": None,
              "Lead Resolve": {"__lead_id": "L1", "__lead_labels": []},
              "U Lead Select": None, "Dedupe": {"__dedupe_key": DK}}
o5, _ = run(new_blu, {}, {"json": {"ok": True}, "nodes": {
    **base_nodes, "SL Forward Email": {"ok": True, "messageId": "<m>", "status": "success"}}},
    "forward SUCCEEDED -> F-key claimed", {"claimed": ["F|" + DK], "out_len": 1}, REPORT)
ok = o5 and ok
o6, _ = run(new_blu, {}, {"json": {}, "nodes": {**base_nodes, "SL Forward Email": None}},
            "skip / non-forward path -> NOTHING claimed", {"claimed": [], "out_len": 1}, REPORT)
ok = o6 and ok
o7, _ = run(new_blu, {}, {"json": {}, "nodes": {
    **base_nodes, "SL Forward Email": {"ok": False, "error": "smtp refused"}}},
    "forward FAILED (ok:false, node continued) -> NOT claimed", {"claimed": []}, REPORT)
ok = o7 and ok

print("\n--- statics: THE REPLAY SCENARIO, end to end ---")
store = {}
_, r1 = run(new_bfe, store, {"json": BODY_JSON,
                             "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                                       "Dedupe": {"__dedupe_key": DK}, "Apply Enrich": None}},
            "1. no-lead reply arrives -> forward proceeds", {"skip": False})
store["F|" + DK] = 1786400000          # what Body Lead Labels Union writes on ok:true
_, r2 = run(new_blu, store, {"json": {"ok": True}, "nodes": {
    **base_nodes, "SL Forward Email": {"ok": True}}},
    "2. forward succeeds -> F-key claimed", {"claimed": ["F|" + DK]}, REPORT)
o8, r3 = run(new_bfe, store, {"json": BODY_JSON,
                              "nodes": {"CONFIG": CFG, "Normalize": {"reply": {}},
                                        "Dedupe": {"__dedupe_key": DK}, "Apply Enrich": None}},
             "3. REPLAY -> CRM retried, ZERO second forward", {"skip": True, "already": True})
ok = o8 and ok
if not ok:
    sys.exit(1)

sd = (wf.get("staticData") or {}).get("global") or {}
seen = sd.get("wf2_seen") or {}
fkey = "F|" + SPECIMEN
print("\n--- planned ---")
print(f"  - Body SL Forward Email  : gate on {fkey.split('|')[0]}|<dedupe_key> "
      f"{'ADD' if need_gate else '(present)'}")
print(f"  - Body Lead Labels Union : claim on forward ok:true "
      f"{'ADD' if need_claim else '(present)'}")
print(f"  - seed specimen F-key    : {fkey}   already_present={fkey in seen}")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_fkey_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))

N["Body SL Forward Email"]["parameters"]["jsCode"] = new_bfe
N["Body Lead Labels Union"]["parameters"]["jsCode"] = new_blu
fresh = ((n8n(f"/api/v1/workflows/{WF2}").get("staticData") or {}).get("global") or {})
fseen = dict(fresh.get("wf2_seen") or {})
fseen[fkey] = int(datetime.now(timezone.utc).timestamp())
body = put_body(wf)
body["staticData"] = {"global": {**fresh, "wf2_seen": fseen}}
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", body)

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
aseen = ((after.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
problems = []
if "__forward_already_sent" not in an["Body SL Forward Email"]["parameters"]["jsCode"]:
    problems.append("gate not applied")
if "'F|' + __k" not in an["Body Lead Labels Union"]["parameters"]["jsCode"]:
    problems.append("claim not applied")
if fkey not in aseen:
    problems.append("specimen F-key not seeded")
if after.get("active") is not wf.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
print(f"  wf2_seen={len(aseen)} entries, F-keys={[k for k in aseen if k.startswith('F|')]}")
sys.exit(1 if problems else 0)
