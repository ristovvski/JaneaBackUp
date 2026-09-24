#!/usr/bin/env python3
"""WF-1 gate twin, part 2: claim only on DELIVERY TO THE TEAM CHANNEL, and rebuild the registry.

This morning's f7be310f already did half of Nik's item 1: label-based suppression is gone from the
alert decision, and the claim moved out of the gate into `M7 Labels Compute`, firing on Slack
ok:true. What is still missing is the CHANNEL condition.

Nik's rule: "first alert" = first DELIVERED TO THE TEAM CHANNEL (C07LTD8UT70). An alert that only
reached ops was not an alert. So the claim needs `ok === true AND channel === TEAM`.

EVIDENCE THIS IS THE RIGHT RESET (full walk of 1,399 executions, 2026-07-23 -> today, 0 unreadable):
  * 99 alerts posted ok:true - ALL 99 to C0B8GCVNR5W (ops), 40 distinct alert keys. NONE to team.
  * 51 suppressions: 40 `already_alerted`, 11 `responded_label` (the label gate, now removed).
  * __alerted_v1 holds 50 entries, every one written at DECISION time by the old gate - the exact
    claim shape Nik's rule rejects. All 50 are explained (40 ops-only, 25 suppressed-only,
    overlapping); 0 unexplained.
  => proven-delivered-to-team = 0, so the rebuilt registry is EMPTY and 50 leads become eligible
     for one real team-channel alert on their next reply.

The channel id is pinned to the TEAM constant rather than read from CONFIG.slack_channel_replies.
They are equal today, but they mean different things: if replies were ever pointed back at ops, a
CONFIG-derived check would silently start "claiming" ops posts as delivery and re-mute everyone.
The rule is about the team seeing it, not about wherever the config currently points.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
TEAM = "C07LTD8UT70"

OLD = "  if (__s && __s.ok === true) {"
NEW = ("  // Nik 2026-08-11: delivery means the TEAM saw it. ok:true alone is not delivery - 99\n"
       "  // historical alerts were ok:true into the OPS channel, and an alert nobody saw was not\n"
       "  // an alert. Pinned to the team id on purpose, NOT CONFIG.slack_channel_replies: if that\n"
       "  // were ever pointed back at ops, a config-derived check would silently re-mute everyone.\n"
       "  const __TEAM = '" + TEAM + "';\n"
       "  if (__s && __s.ok === true && __s.channel === __TEAM) {")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


# The wrapped ORIGINAL reads CONFIG / M7 Person Get / M7 Build / M7 Lead Get, and returns a bare
# OBJECT, not an array. Both facts were discovered by the harness refusing to invent a node it was
# not given - a permissive mock would have "passed" while testing nothing. `lead_present=False`
# exercises the original's own no-lead early return, because the claim must fire on that path too.
CFG_MOCK = ("{ fields: { stage: 'STAGE' }, stageRank: { Replied: 4, Connected: 2 },"
            " labels: { responded: 'R', connected: 'C', cold: 'K' } }")


def run_case(js, label, want, slack, gate_key="K1", reg=None, lead_present=True):
    leads = ([{"id": "L1", "is_archived": False, "add_time": "2026-08-01T00:00:00Z",
               "label_ids": []}] if lead_present else [])
    harness = f"""
const __sd = {{ __alerted_v1: {json.dumps(reg or {})}, seen: {{ keepme: 1 }} }};
const $getWorkflowStaticData = () => __sd;
const $input = {{ all: () => [{{ json: {{ passthrough: true }} }}] }};
const $json = {{ passthrough: true }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: {CFG_MOCK} }} }};
  if (nm === 'M7 Person Get') return {{ item: {{ json: {{ data: {{ id: 7, custom_fields: {{}} }} }} }} }};
  if (nm === 'M7 Build') return {{ item: {{ json: {{ targetStage: 'Replied' }} }} }};
  if (nm === 'M7 Lead Get') return {{ item: {{ json: {{ data: {json.dumps(leads)} }} }} }};
  if (nm === 'M7 Critical Slack') {{
    const s = {json.dumps(slack)};
    if (s === null) throw new Error('node did not run on this path');
    return {{ item: {{ json: s }} }};
  }}
  if (nm === 'M7 Alert Gate') return {{ item: {{ json: {{ __alert_key: {json.dumps(gate_key)} }} }} }};
  throw new Error('absent: ' + nm);
}};
const __out = (() => {{
{js}
}})();
console.log(JSON.stringify({{
  claimed: Object.keys(__sd.__alerted_v1).length > 0,
  key: Object.keys(__sd.__alerted_v1)[0] || null,
  seen_preserved: !!(__sd.seen && __sd.seen.keepme),
  returned: !!__out && typeof __out === 'object',
  lead_id: (__out && __out.json) ? (__out.json.lead_id || null) : null,
  invalid: !!(__out && __out.json && __out.json.__invalid)
}}));
"""
    tmp = os.path.join(HERE, "_wf1claim_case.js")
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
ap.add_argument("--reset-registry", action="store_true",
                help="rebuild __alerted_v1 from delivery evidence (currently: empty)")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF1}")
N = {n["name"]: n for n in wf["nodes"]}
comp = N["M7 Labels Compute"]["parameters"]["jsCode"]
if "__alerted_v1" not in comp:
    raise SystemExit("M7 Labels Compute does not carry the claim - run patch_wf1_gate_delivery first")
already = "__TEAM" in comp
new_js = comp if already else comp.replace(OLD, NEW)
if not already and OLD not in comp:
    raise SystemExit(f"anchor missing, refusing to patch blind:\n  {OLD}")

print(f"WF-1 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")
print("\n--- statics: EXECUTING the claim body ---")
ok = True
ok = run_case(new_js, "posted ok:true to the TEAM channel -> CLAIMS",
              {"claimed": True, "key": "K1", "seen_preserved": True,
               "returned": True, "lead_id": "L1"},
              {"ok": True, "channel": TEAM}) and ok
ok = run_case(new_js, "posted ok:true to OPS only -> does NOT claim (Nik's rule)",
              {"claimed": False, "seen_preserved": True, "returned": True, "lead_id": "L1"},
              {"ok": True, "channel": "C0B8GCVNR5W"}) and ok
ok = run_case(new_js, "post FAILED (ok:false) -> does NOT claim",
              {"claimed": False, "returned": True},
              {"ok": False, "channel": TEAM, "error": "channel_not_found"}) and ok
ok = run_case(new_js, "suppressed path: alert node never ran -> no claim, no throw",
              {"claimed": False, "returned": True}, None) and ok
ok = run_case(new_js, "ok:true to team but NO alert key -> nothing claimed",
              {"claimed": False, "returned": True}, {"ok": True, "channel": TEAM},
              gate_key=None) and ok
ok = run_case(new_js, "already-claimed key stays claimed (idempotent)",
              {"claimed": True, "key": "K1", "returned": True},
              {"ok": True, "channel": TEAM}, reg={"K1": "2026-08-01T00:00:00Z"}) and ok
ok = run_case(new_js, "original's no-lead path still returns __invalid AND still claims",
              {"claimed": True, "key": "K1", "invalid": True, "returned": True},
              {"ok": True, "channel": TEAM}, lead_present=False) and ok
ok = run_case(new_js, "no-lead path + ops-only post -> __invalid, and NO claim",
              {"claimed": False, "invalid": True, "returned": True},
              {"ok": True, "channel": "C0B8GCVNR5W"}, lead_present=False) and ok
if not ok:
    sys.exit(1)

sd = (wf.get("staticData") or {}).get("global") or {}
reg = sd.get("__alerted_v1") or {}
plan_path = os.path.join(HERE, "wf1-release-evidence", "wf1_registry_seed.json")
seed = json.load(open(plan_path, encoding="utf-8"))["seed"] if os.path.exists(plan_path) else {}

print(f"\n--- planned ---")
if not already:
    print("  - M7 Labels Compute -> claim requires channel === TEAM")
else:
    print("  (claim already channel-gated)")
if a.reset_registry:
    print(f"  - __alerted_v1 REBUILD: {len(reg)} -> {len(seed)} entries "
          f"({len(reg) - len(seed)} leads become eligible for one real team alert)")
    print(f"    other staticData.global keys preserved: {[k for k in sd if k != '__alerted_v1']}")
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_channelclaim_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(wf, indent=2, ensure_ascii=False))

N["M7 Labels Compute"]["parameters"]["jsCode"] = new_js
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF1}/deactivate", "POST", {})
try:
    body = put_body(wf)
    if a.reset_registry:
        # PUT does carry staticData (verified on a throwaway workflow). Deactivating first is what
        # makes this safe: WF-1 writes this same registry on every alert, so a live PUT could
        # clobber a concurrent claim.
        fresh = ((n8n(f"/api/v1/workflows/{WF1}").get("staticData") or {}).get("global") or {})
        body["staticData"] = {"global": {**fresh, "__alerted_v1": dict(seed)}}
    d = stripped_keys(wf)
    if d:
        print(f"stripping UI-only settings keys: {d}")
    n8n(f"/api/v1/workflows/{WF1}", "PUT", body)
finally:
    if was:
        n8n(f"/api/v1/workflows/{WF1}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF1}")
an = {x["name"]: x for x in after["nodes"]}
asd = (after.get("staticData") or {}).get("global") or {}
problems = []
if "__TEAM" not in an["M7 Labels Compute"]["parameters"]["jsCode"]:
    problems.append("claim not channel-gated")
if "responded_label" in an["M7 Alert Gate"]["parameters"]["jsCode"]:
    problems.append("label suppression still in the gate")
if a.reset_registry and len(asd.get("__alerted_v1") or {}) != len(seed):
    problems.append(f"registry={len(asd.get('__alerted_v1') or {})} expected {len(seed)}")
if a.reset_registry and "seen" in sd and "seen" not in asd:
    problems.append("staticData.seen was lost")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')} (was {was})")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])} registry={len(asd.get('__alerted_v1') or {})} "
      f"staticData keys={list(asd.keys())}")
sys.exit(1 if problems else 0)
