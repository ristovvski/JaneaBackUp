#!/usr/bin/env python3
"""OOO-GATE: an autoresponder is not engagement. Melisa's request, Nik's confirmation.

DESIGN NOTE THAT MADE THIS SMALL. Our LLM category is NOT available when the alert fires -
`Classify Parse` runs at position #29, `First Reply Gate` at #21, so gating the alert on the LLM
would have needed the graph reordered. But SMARTLEAD ships its own category on the webhook
(`reply_category: 6`), and `Normalize` (#6) already maps it to the string "Out Of Office". Gating on
that is early, free, and independent of the LLM - which also means an LLM outage cannot start
leaking OOO alerts.

Behaviour when Smartlead says OOO:
  * NO team alert, and the lead's ONE-ALERT SLOT IS NOT CONSUMED. This is the critical one: when
    the human returns (Aug 14 / 17 / 19) and replies for real, THAT reply must alert as their first.
    The slot survives for free because the registry is only written when Reply Alert returns
    ok:true - no alert, no claim.
  * NO forward. Already true in practice via the LLM's __forwardable=false, but that is the LLM
    deciding; this makes it Smartlead's category deciding, so it holds even if the LLM misfires.
  * NO "3. Responded" label - which ALSO suppresses the Handover. There is no handover node in
    WF-2: Marci's Pipedrive automation triggers off that label, so not writing it is the fix.
  * Activity STILL written (the record is free and useful) and dedupe/F-key claims are NORMAL,
    because processed is processed.

FAIL-OPEN, per Nik: if reply_category is missing or unreadable, treat it as a REAL reply and
forward+alert. A missed vacation notice is annoying; a missed real reply is the Marine class.

Fixtures are the three REAL payloads from today - pii-d5d243f4@example.invalid (returns Aug 19),
pii-9f313a1a@example.invalid (Aug 14) and pii-08ce5db0@example.invalid (Aug 17). Nik named two; the sweep found
three, and the third is repaired identically.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
OOO_LEADS = {"4ead0900-90d6-11f1-b07d-7faf1dbb463a": "pii-d5d243f4@example.invalid",
             "51c9f9d0-8538-11f1-8c6a-ef2edb9d15ea": "pii-9f313a1a@example.invalid",
             "17c6d0b0-8541-11f1-998a-a9f867fdc12c": "pii-08ce5db0@example.invalid"}

# One definition, used by every suppression, so they can never disagree with each other.
OOO_HELPER = """
// OOO-GATE: Smartlead's own reply_category, available from Normalize (#6) - long before the alert
// decision (#21) and independent of our LLM (#29), so an LLM outage cannot leak OOO alerts.
// FAIL-OPEN by design: unknown/missing category => treat as a REAL reply.
const __isOOO = (() => {
  try {
    const c = String(($('Normalize').item.json || {}).reply_category ?? '').trim().toLowerCase();
    if (!c) return false;
    const auto = ['out of office', 'ooo', 'auto reply', 'auto-reply', 'automatic reply',
                  'autoreply', 'vacation', 'away'];
    return auto.indexOf(c) !== -1;
  } catch (e) { return false; }
})();
"""

GATE_OLD = """const should = alertEvery ? true : (!key ? true : !already);
return [{ json: { ...$json, __should_alert: should, __alert_key: key,
  __alert_reason: alertEvery ? 'alert_every_reply'
    : (!key ? 'fail_open_no_key' : (already ? 'already_delivered' : 'first_reply')),"""
GATE_NEW = OOO_HELPER + """
// An autoresponder is not engagement, and it must NOT burn the lead's single alert. Because the
// registry is written only when Reply Alert returns ok:true, suppressing here leaves the slot
// intact automatically - the human's real reply on their return still counts as their first.
const should = __isOOO ? false
  : (alertEvery ? true : (!key ? true : !already));
return [{ json: { ...$json, __should_alert: should, __alert_key: key, __ooo: __isOOO,
  __alert_reason: __isOOO ? 'ooo_no_alert'
    : (alertEvery ? 'alert_every_reply'
    : (!key ? 'fail_open_no_key' : (already ? 'already_delivered' : 'first_reply'))),"""

LBL_OLD = """const target = [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];"""
LBL_NEW = OOO_HELPER + """
// '3. Responded' is ALSO the trigger for Marci's Handover automation, so withholding it is what
// suppresses the handover - there is no handover node in this workflow to switch off. cold and
// connected still apply: an autoreply does prove the mailbox is live.
const target = __isOOO
  ? [CFG.labels.cold, CFG.labels.connected]
  : [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];"""

FWD_OLD = """  __skip: __already_forwarded || !body.to_emails || (!body.message_id && !body.stats_id),"""
FWD_NEW = """  __skip: __isOOO || __already_forwarded || !body.to_emails
          || (!body.message_id && !body.stats_id),
  __forward_ooo: __isOOO,"""
# The skip line above USES __isOOO, so the helper that defines it has to be inserted separately -
# ahead of the return block. Patching only the skip line left __isOOO undefined and the node dead;
# the statics caught it because they EXECUTE the body rather than checking it parses.
FWD_HELPER_ANCHOR = "const __fkey = (() => {"


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
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:160].decode("utf-8", "replace")


def run(js, label, mocks, want, report):
    src = f"""
const __sd = {{ __alert_delivered: {json.dumps(mocks.get('reg', {}))},
                wf2_seen: {json.dumps(mocks.get('seen', {}))} }};
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
{report}
"""
    tmp = os.path.join(HERE, "_ooo_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
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

wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

gate = N["First Reply Gate"]["parameters"]["jsCode"]
lbl = N["Body Lead Labels Union"]["parameters"]["jsCode"]
fwd = N["Body SL Forward Email"]["parameters"]["jsCode"]
for nm, src, anchor in (("First Reply Gate", gate, GATE_OLD),
                        ("Body Lead Labels Union", lbl, LBL_OLD),
                        ("Body SL Forward Email", fwd, FWD_OLD)):
    if "__isOOO" not in src and anchor not in src:
        raise SystemExit(f"{nm}: anchor missing, refusing to patch blind")
new_gate = gate if "__isOOO" in gate else gate.replace(GATE_OLD, GATE_NEW)
new_lbl = lbl if "__isOOO" in lbl else lbl.replace(LBL_OLD, LBL_NEW)
if "__isOOO" in fwd:
    new_fwd = fwd
else:
    if FWD_HELPER_ANCHOR not in fwd:
        raise SystemExit("Body SL Forward Email: helper anchor missing, refusing to patch blind")
    new_fwd = (fwd.replace(FWD_HELPER_ANCHOR, OOO_HELPER + "\n" + FWD_HELPER_ANCHOR)
                  .replace(FWD_OLD, FWD_NEW))

CFG = {"labels": {"cold": "K", "connected": "C2", "responded": RESPONDED},
       "fields": {}, "alert_registry_max_age_sec": 7776000, "flags": {}}
OOO_N = {"reply_category": "Out Of Office", "lead": {"email": "pii-d5d243f4@example.invalid"}, "reply": {}}
REAL_N = {"reply_category": "Interested", "lead": {"email": "pii-5e6b1c2a@example.invalid"}, "reply": {}}
NONE_N = {"lead": {"email": "x@y.z"}, "reply": {}}

print("\n--- statics: alert gate (fixtures = today's REAL payloads) ---")
GR = ("console.log(JSON.stringify({ should: __out[0].json.__should_alert,"
      " reason: __out[0].json.__alert_reason, ooo: __out[0].json.__ooo,"
      " reg_after: Object.keys(__sd.__alert_delivered) }));")
ok = True
for who, norm in (("pii-d5d243f4@example.invalid (returns Aug 19)", OOO_N),
                  ("pii-9f313a1a@example.invalid (Aug 14)",
                   {**OOO_N, "lead": {"email": "pii-9f313a1a@example.invalid"}}),
                  ("pii-08ce5db0@example.invalid (Aug 17)",
                   {**OOO_N, "lead": {"email": "pii-08ce5db0@example.invalid"}})):
    ok = run(new_gate, f"OOO {who} -> NO alert, slot NOT consumed",
             {"json": {"__lead_id": "L1"}, "nodes": {"CONFIG": CFG, "Normalize": norm}, "reg": {}},
             {"should": False, "reason": "ooo_no_alert", "ooo": True, "reg_after": []}, GR) and ok
ok = run(new_gate, "the SAME lead replies for real later -> alerts as their FIRST",
         {"json": {"__lead_id": "L1"}, "nodes": {"CONFIG": CFG, "Normalize": REAL_N}, "reg": {}},
         {"should": True, "reason": "first_reply", "ooo": False}, GR) and ok
ok = run(new_gate, "real reply, already delivered -> still suppressed as repeat",
         {"json": {"__lead_id": "L1"}, "nodes": {"CONFIG": CFG, "Normalize": REAL_N},
          "reg": {"L1": 1786400000}},
         {"should": False, "reason": "already_delivered"}, GR) and ok
ok = run(new_gate, "category MISSING -> FAIL-OPEN, treated as a real reply",
         {"json": {"__lead_id": "L1"}, "nodes": {"CONFIG": CFG, "Normalize": NONE_N}, "reg": {}},
         {"should": True, "reason": "first_reply", "ooo": False}, GR) and ok
ok = run(new_gate, "Normalize unreadable -> FAIL-OPEN",
         {"json": {"__lead_id": "L1"}, "nodes": {"CONFIG": CFG, "Normalize": None}, "reg": {}},
         {"should": True, "ooo": False}, GR) and ok

print("\n--- statics: labels (no Responded => no Handover) ---")
LR = ("console.log(JSON.stringify({ union: __out[0].json.__label_union,"
      " responded: (__out[0].json.__label_union || []).indexOf("
      + json.dumps(RESPONDED) + ") !== -1, skip: __out[0].json.__skip }));")
lbl_nodes = {"CONFIG": CFG, "Apply Enrich": None, "Mark DNC": None, "U Mark DNC": None,
             "Merge Reply Ctx": None, "U Lead Select": None, "SL Forward Email": None,
             "Dedupe": {"__dedupe_key": "K"},
             "Lead Resolve": {"__lead_id": "L1", "__lead_labels": []}}
ok = run(new_lbl, "OOO -> cold+connected only, NO '3. Responded' (=> no Handover)",
         {"json": {}, "nodes": {**lbl_nodes, "Normalize": OOO_N}},
         {"responded": False}, LR) and ok
ok = run(new_lbl, "real reply -> '3. Responded' still applied",
         {"json": {}, "nodes": {**lbl_nodes, "Normalize": REAL_N}},
         {"responded": True}, LR) and ok

print("\n--- statics: forward ---")
FR = ("console.log(JSON.stringify({ skip: __out[0].json.__skip,"
      " ooo: __out[0].json.__forward_ooo }));")
fwd_nodes = {"CONFIG": CFG, "Apply Enrich": None, "Dedupe": {"__dedupe_key": "K"}}
ok = run(new_fwd, "OOO -> NO forward to the owner",
         {"json": {"__forward_to": "rune@janeasystems.com", "__message_id": "M", "__stats_id": "S"},
          "nodes": {**fwd_nodes, "Normalize": OOO_N}}, {"skip": True}, FR) and ok
ok = run(new_fwd, "real reply -> forward still goes",
         {"json": {"__forward_to": "rune@janeasystems.com", "__message_id": "M", "__stats_id": "S"},
          "nodes": {**fwd_nodes, "Normalize": REAL_N}}, {"skip": False}, FR) and ok
if not ok:
    sys.exit(1)

sd = (wf.get("staticData") or {}).get("global") or {}
reg = sd.get("__alert_delivered") or {}
print("\n--- planned ---")
print("  - First Reply Gate       : OOO -> no alert, slot preserved")
print("  - Body Lead Labels Union : OOO -> no '3. Responded' (=> no Handover)")
print("  - Body SL Forward Email  : OOO -> no forward")
print("  REPAIR of today's three OOO leads:")
for lid, em in OOO_LEADS.items():
    st, d = pd(f"/v1/leads/{lid}")
    labels = ((d or {}).get("data") or {}).get("label_ids") or [] if isinstance(d, dict) else []
    print(f"     {em:<28} slot_in_registry={lid in reg}  responded_label={RESPONDED in labels}")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_ooo_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))

N["First Reply Gate"]["parameters"]["jsCode"] = new_gate
N["Body Lead Labels Union"]["parameters"]["jsCode"] = new_lbl
N["Body SL Forward Email"]["parameters"]["jsCode"] = new_fwd
fresh = ((n8n(f"/api/v1/workflows/{WF2}").get("staticData") or {}).get("global") or {})
freg = dict(fresh.get("__alert_delivered") or {})
released = [k for k in list(OOO_LEADS) if freg.pop(k, None) is not None]
body = put_body(wf)
body["staticData"] = {"global": {**fresh, "__alert_delivered": freg}}
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
print(f"  releasing alert slots: {released}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", body)

print("\n  removing '3. Responded' from today's OOO leads")
for lid, em in OOO_LEADS.items():
    st, d = pd(f"/v1/leads/{lid}")
    L = (d or {}).get("data") or {} if isinstance(d, dict) else {}
    labels = L.get("label_ids") or []
    if RESPONDED not in labels:
        print(f"     {em}: not present, nothing to do")
        continue
    st2, _ = pd(f"/v1/leads/{lid}", "PATCH",
                {"label_ids": [x for x in labels if x != RESPONDED]})
    st3, d3 = pd(f"/v1/leads/{lid}")
    now = ((d3 or {}).get("data") or {}).get("label_ids") or []
    print(f"     {em}: PATCH {st2}, responded now {RESPONDED in now}")

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
areg = ((after.get("staticData") or {}).get("global") or {}).get("__alert_delivered") or {}
problems = []
for nm in ("First Reply Gate", "Body Lead Labels Union", "Body SL Forward Email"):
    if "__isOOO" not in an[nm]["parameters"]["jsCode"]:
        problems.append(f"{nm} not patched")
for lid in OOO_LEADS:
    if lid in areg:
        problems.append(f"slot still held: {lid}")
if after.get("active") is not wf.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}  __alert_delivered={len(areg)}")
sys.exit(1 if problems else 0)
