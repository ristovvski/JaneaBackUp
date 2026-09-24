#!/usr/bin/env python3
"""P0-1b - move WF-2's dedupe claim from DECISION time to AFTER the work succeeded.

BUILD ONLY. `--deploy` is deliberately gated on two things (Nik, 2026-08-11):
  * the auditor's independent spot-check availability, and
  * an observed clean first wave hour.
Running this without --deploy writes nothing and just proves the bodies.

THE DEFECT. `Dedupe` line 21: `if (!duplicate) store.wf2_seen[key] = nowSec;` - claimed before any
work happens. If the execution then crashes, the event is permanently unreplayable: dedupe's 48h
retention is >= WF-2R's 48h lookback, so it ages out of the reconciler's reach while still being
suppressed. Proven by exec 14966 (Marine's OOO): crashed on the broken `Body Reply Alert`, claim
already written, unrecoverable by the reconciler that exists to recover it.

WHY IT IS NOT A ONE-LINE MOVE: no node is reachable from every Switch Event branch, and terminal
!= success. Three success terminals are httpRequest and one is Slack - none can carry code - so
four new Code nodes are required. That is graph surgery (+4 nodes, +4 connections) on a live
workflow, which is why it is gated.

RE-DERIVED AGAINST ce1a8355, AND IT CHANGED THE DESIGN. `Bounce Note` (httpRequest) and
`Nurture Alert` (slack) both carry onError: continueRegularOutput - they continue even when the
write FAILS. A claim that fires merely because it was reached would therefore claim on failure:
the event is silently lost AND the failure stays invisible, which is strictly worse than today's
bug. So those claims inspect the RESPONSE, exactly like the WF-1 gate's `ok === true` rule.
`Ops Warn Unknown Event` does NOT claim, per Nik: an unknown event must stay noisy and replayable.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"

OLD_CLAIM = "if (!duplicate) store.wf2_seen[key] = nowSec;"
NEW_CLAIM = """// P0-1b: the claim MOVED to the success terminals. Claiming here - before any work - made a
// crashed execution permanently unreplayable, because dedupe's 48h retention is >= WF-2R's 48h
// lookback: the event ages out of the reconciler while still being suppressed by this store.
// `duplicate` is still computed and `__dedupe_key` still emitted; only the write left.
// (The first-SENT memo below is a different key and stays - it is a sequence memo, not a claim.)"""

# Appended to Code nodes that are already success terminals, via the proven IIFE-wrap.
CLAIM_INLINE = """
// P0-1b claim-after-success: reaching this node means the branch's work completed.
try {
  const __k = $('Dedupe').item.json.__dedupe_key;
  if (__k) {
    const __sd = $getWorkflowStaticData('global');
    (__sd.wf2_seen = __sd.wf2_seen || {})[__k] = Math.floor(Date.now() / 1000);
  }
} catch (e) { /* not on this branch */ }
"""

# Standalone Claim nodes after terminals that cannot carry code.
# `ok_expr` must be TRUE only when the upstream write actually landed.
CLAIM_NODE_TMPL = """// P0-1b claim-after-success, guarding `{after}`.
// {why}
const __items = $input.all();
const __ok = (() => {{ try {{ return ({ok_expr}); }} catch (e) {{ return false; }} }})();
if (__ok) {{
  try {{
    const __k = $('Dedupe').item.json.__dedupe_key;
    if (__k) {{
      const __sd = $getWorkflowStaticData('global');
      (__sd.wf2_seen = __sd.wf2_seen || {{}})[__k] = Math.floor(Date.now() / 1000);
    }}
  }} catch (e) {{ /* no key - leave it replayable */ }}
}}
return __items;
"""

NEW_NODES = [
    ("Claim SENT", "Lead Create",
     "Lead Create has onError=None, so arriving here already means a 2xx - but assert the created "
     "id anyway rather than trusting reachability.",
     "$json.data && $json.data.id"),
    ("Claim Bounce", "Bounce Note",
     "Bounce Note carries onError: continueRegularOutput - it CONTINUES when the POST fails. "
     "Claiming on reachability would claim on failure: event lost AND failure invisible.",
     "$json.success === true || ($json.data && $json.data.id)"),
    ("Claim Unsub", "U Lead DNC Label",
     "httpRequest, onError=None. Assert the PATCH returned a lead rather than trusting arrival.",
     "$json.success === true || ($json.data && $json.data.id)"),
    ("Claim Nurture", "Nurture Alert",
     "Slack node with onError: continueRegularOutput. Slack reports failure in the BODY (ok:false) "
     "with a 200 - the exact shape that hid 25 failed posts for eleven days.",
     "$json.ok === true"),
]
INLINE_SITES = ["NoOp Lead Exists", "NoOp Nurture SENT", "NoOp Repeat SENT", "Reply CRM Done"]


def n8n(path, method="GET", body=None, attempt=0):
    """Retries transient auth/rate failures, and names the failing path when it gives up.

    A bare 401 killed the first attempt at this deploy. Nothing was half-applied (the failure landed
    before the PUT), but the shape is the dangerous one: a transient error BETWEEN deactivate and
    PUT leaves the workflow off. This engagement has already had one outage of exactly that shape,
    so the deploy path retries instead of trusting a single call, and the caller is told WHERE.
    """
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        # 401 here is NOT credentials - the same key reads fine and the same call succeeds
        # standalone. It tracks STATE-CHANGING calls in quick succession (the wrapper pauses two
        # pollers immediately before this deploy's deactivate). 93s of backoff was not enough;
        # standalone succeeded about two minutes after the last failure, so be patient rather than
        # clever. A deploy that waits is free; a deploy that half-applies is an outage.
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 5:
            wait = 15 * (2 ** attempt)
            print(f"   HTTP {e.code} on {method} {path[:60]} - retry in {wait}s "
                  f"(attempt {attempt + 1})", flush=True)
            time.sleep(wait)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code} "
                         f"{e.read()[:200].decode('utf-8', 'replace')}")


def run_js(js, label, want):
    tmp = os.path.join(HERE, "_p01b_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-240:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return not bad


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
ap.add_argument("--no-toggle", action="store_true",
                help="PUT onto the live workflow instead of deactivate/PUT/activate")
a = ap.parse_args()

import copy

wf = n8n(f"/api/v1/workflows/{WF2}")
WF_ORIGINAL = copy.deepcopy(wf)          # pre-change snapshot; no second GET needed for the backup
N = {n["name"]: n for n in wf["nodes"]}
ded = N["Dedupe"]["parameters"]["jsCode"]
if OLD_CLAIM not in ded:
    raise SystemExit("Dedupe: claim line not found - refusing to patch blind")
ded_new = ded.replace(OLD_CLAIM, NEW_CLAIM)

print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])}\n")
ok = True

# ---- 1. Dedupe no longer claims (auditor spot-check #2)
DEDUPE_HARNESS = """
const __sd = { wf2_seen: %s };
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => ({ item: { json: nm === 'CONFIG'
  ? { dedupe_max_age_sec: 172800 }
  : %s } });
const __out = (() => {
%s
})();
console.log(JSON.stringify({
  dup: __out[0].json.__duplicate,
  key_claimed: Object.prototype.hasOwnProperty.call(__sd.wf2_seen, __out[0].json.__dedupe_key),
  key: __out[0].json.__dedupe_key,
  store_keys: Object.keys(__sd.wf2_seen).length
}));
"""
EV = {"event": "REPLIED", "campaign_id": 3686187, "sl_lead_id": "4306240392",
      "timestamp": "2026-08-11T10:14:32.000Z"}
KEY = "REPLIED|3686187|4306240392|" + str(1786443272000)

print("--- statics: Dedupe (the claim must be GONE) ---")
ok = run_js(DEDUPE_HARNESS % ("{}", json.dumps(EV), ded_new),
            "virgin event -> NOT claimed, so a crash stays replayable (spot-check #2)",
            {"dup": False, "key_claimed": False, "store_keys": 0}) and ok
ok = run_js(DEDUPE_HARNESS % (json.dumps({KEY: 1786443000}), json.dumps(EV), ded_new),
            "key already claimed -> still detected as duplicate",
            {"dup": True, "key_claimed": True}) and ok
ok = run_js(DEDUPE_HARNESS % (json.dumps({"stale|k": 1}), json.dumps(EV), ded_new),
            "age rotation still prunes a stale key",
            {"dup": False, "store_keys": 0}) and ok
ok = run_js(DEDUPE_HARNESS % ("{}", json.dumps({**EV, "event": "SENT"}), ded_new),
            "SENT: the first-sent MEMO still writes (it is a memo, not a claim)",
            {"dup": False, "key_claimed": False, "store_keys": 1}) and ok

# ---- 2. the claim bodies
CLAIM_HARNESS = """
const __sd = { wf2_seen: {} };
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => { if (nm === 'Dedupe') { %s } throw new Error('absent: ' + nm); };
const $json = %s;
const $input = { all: () => [{ json: $json }] };
const __out = (() => {
%s
})();
console.log(JSON.stringify({
  claimed: Object.keys(__sd.wf2_seen).length > 0,
  key: Object.keys(__sd.wf2_seen)[0] || null,
  passthrough: Array.isArray(__out) ? __out.length : -1
}));
"""
DEDUPE_OK = "return { item: { json: { __dedupe_key: 'K1' } } };"
DEDUPE_MISSING = "throw new Error('not on this branch');"

print("\n--- statics: standalone Claim nodes (response-inspecting) ---")
for name, after, why, ok_expr in NEW_NODES:
    body = CLAIM_NODE_TMPL.format(after=after, why=why, ok_expr=ok_expr)
    good = ({"ok": True, "data": {"id": 1}, "success": True})
    bad_resp = ({"ok": False, "error": "channel_not_found", "success": False, "data": None})
    ok = run_js(CLAIM_HARNESS % (DEDUPE_OK, json.dumps(good), body),
                f"{name}: upstream SUCCEEDED -> claimed",
                {"claimed": True, "key": "K1", "passthrough": 1}) and ok
    ok = run_js(CLAIM_HARNESS % (DEDUPE_OK, json.dumps(bad_resp), body),
                f"{name}: upstream FAILED but continued -> NOT claimed, stays replayable",
                {"claimed": False, "passthrough": 1}) and ok
    ok = run_js(CLAIM_HARNESS % (DEDUPE_MISSING, json.dumps(good), body),
                f"{name}: no Dedupe on this path -> no claim, no throw",
                {"claimed": False, "passthrough": 1}) and ok

print("\n--- statics: inline claim appended to existing Code terminals (EXECUTED) ---")
# Printing "IIFE-wrapped, N lines" proves nothing - that is the shape that let a syntax-valid but
# broken `Body Reply Alert` ship. Each wrapped body is RUN, and its original output is compared
# against the unwrapped original so the wrap is shown to be behaviour-preserving.
INLINE_HARNESS = """
const __sd = { wf2_seen: {} };
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => { if (nm === 'Dedupe') { %s } throw new Error('absent: ' + nm); };
const $json = { any: 'thing' };
const $input = { all: () => [{ json: $json }] };
const __out = (() => {
%s
})();
console.log(JSON.stringify({
  claimed: Object.keys(__sd.wf2_seen).length > 0,
  key: Object.keys(__sd.wf2_seen)[0] || null,
  out: JSON.stringify(__out)
}));
"""
for site in INLINE_SITES:
    orig = N[site]["parameters"]["jsCode"]
    wrapped = ("const __items = (() => {\n" + orig + "\n})();\n" + CLAIM_INLINE
               + "\nreturn __items;")
    base = os.path.join(HERE, "_p01b_base.js")
    with open(base, "w", encoding="utf-8") as f:
        f.write(INLINE_HARNESS % (DEDUPE_MISSING, orig))
    b = subprocess.run(["node", base], capture_output=True, text=True, encoding="utf-8")
    os.remove(base)
    if b.returncode != 0:
        print(f"  [FAIL] {site}: ORIGINAL body will not run in the harness: "
              f"{(b.stderr or '').strip()[-160:]}")
        ok = False
        continue
    original_out = json.loads(b.stdout.strip())["out"]
    ok = run_js(INLINE_HARNESS % (DEDUPE_OK, wrapped),
                f"{site}: wrapped -> claims AND returns exactly what the original returned",
                {"claimed": True, "key": "K1", "out": original_out}) and ok
    ok = run_js(INLINE_HARNESS % (DEDUPE_MISSING, wrapped),
                f"{site}: wrapped, no Dedupe -> no claim, output still unchanged",
                {"claimed": False, "out": original_out}) and ok

print("\n--- NOT claimed, by design ---")
print("  Ops Warn Unknown Event  - stays noisy and replayable (Nik's call)")
print("  Ops Warn No Lead / Ops Warn Classify / Shadow Log - failure or shadow paths")

print(f"\nSTATICS: {'ALL PASS' if ok else 'FAILURES ABOVE'}")
print("\n--- planned graph change (NOT applied) ---")
print(f"  Dedupe        : claim line removed")
for name, after, _, _ in NEW_NODES:
    print(f"  + {name:<14}: new Code node after `{after}`")
for s in INLINE_SITES:
    print(f"  {s:<14}: IIFE-wrap + inline claim")
print(f"  net: +{len(NEW_NODES)} nodes, +{len(NEW_NODES)} connections "
      f"({len(wf['nodes'])} -> {len(wf['nodes']) + len(NEW_NODES)})")
if not ok:
    sys.exit(1)
if not a.deploy:
    print("\n--deploy NOT given: nothing written.")
    sys.exit(0)

# ---------------------------------------------------------------- apply the graph change
CODE_TYPE = "n8n-nodes-base.code"
tv = max((n.get("typeVersion") or 2) for n in wf["nodes"] if n["type"] == CODE_TYPE)
existing = {n["name"] for n in wf["nodes"]}
conns = wf["connections"]

wf_nodes_before = len(wf["nodes"])
N["Dedupe"]["parameters"]["jsCode"] = ded_new
for site in INLINE_SITES:
    orig = N[site]["parameters"]["jsCode"]
    if "__dedupe_key" not in orig:
        N[site]["parameters"]["jsCode"] = ("const __items = (() => {\n" + orig + "\n})();\n"
                                           + CLAIM_INLINE + "\nreturn __items;")
for i, (name, after, why, ok_expr) in enumerate(NEW_NODES):
    if name in existing:
        print(f"  ({name} already present - skipping)")
        continue
    ax, ay = (N[after].get("position") or [0, 0])[:2]
    wf["nodes"].append({
        "parameters": {"jsCode": CLAIM_NODE_TMPL.format(after=after, why=why, ok_expr=ok_expr)},
        "id": f"c1a1m000-0000-4000-8000-00000000000{i + 1}",
        "name": name, "type": CODE_TYPE, "typeVersion": tv,
        "position": [ax + 220, ay + 60],
    })
    conns.setdefault(after, {}).setdefault("main", [[]])
    while len(conns[after]["main"]) < 1:
        conns[after]["main"].append([])
    conns[after]["main"][0] = (conns[after]["main"][0] or []) + [
        {"node": name, "type": "main", "index": 0}]

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_p01b_{stamp}.json"), "w",
          encoding="utf-8") as f:
    # The pre-change snapshot was deep-copied at read time, so the backup costs no extra GET.
    # Re-reading here would also be WRONG now: `wf` has already been mutated in memory above, and
    # a fresh read burns a call against whatever is throttling this key.
    f.write(json.dumps(WF_ORIGINAL, indent=2, ensure_ascii=False))

was = wf.get("active")
# --no-toggle: PUT straight onto the ACTIVE workflow.
#
# The deactivate-first protocol exists because a REJECTED PUT after a successful deactivate leaves
# the workflow off - that is how WF-1 went down for ~90s earlier this week. But WF-2's deactivate is
# now the call that reproducibly 401s (while GET, and both pollers' deactivates, succeed). Toggling
# is not the safety property; NOT LEAVING IT OFF is. Skipping the toggle removes the only step that
# can strand it: a rejected PUT on an active workflow changes nothing and leaves it running.
if was and not a.no_toggle:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
elif was:
    print("  --no-toggle: PUT onto the live workflow; no deactivate window exists to be stranded in")
try:
    d = stripped_keys(wf)
    if d:
        print(f"stripping UI-only settings keys: {d}")
    _body = put_body(wf)
    # A hand-rebuilt payload of the SAME shape (149 nodes, 203,084 bytes) PUTs fine, twelve times
    # over, while this one 401s. So the difference is in what this script actually sends - dump it
    # rather than reason about it.
    _dump = os.path.join(HERE, "wf1-release-evidence", "p01b_put_body.json")
    with open(_dump, "w", encoding="utf-8") as _f:
        json.dump(_body, _f, ensure_ascii=False)
    print(f"  payload: {len(json.dumps(_body))} bytes, {len(_body['nodes'])} nodes, "
          f"top-level keys {sorted(_body.keys())}")
    print(f"  dumped to {_dump}")
    n8n(f"/api/v1/workflows/{WF2}", "PUT", _body)
finally:
    # Reactivation is the step that must not be allowed to fail quietly: if the PUT threw, this is
    # the only thing standing between a transient error and a live workflow left switched off.
    # Under --no-toggle there is nothing to restore, but it is still ASSERTED below.
    if was and not a.no_toggle:
        for _ in range(6):
            try:
                n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})
                if n8n(f"/api/v1/workflows/{WF2}").get("active"):
                    break
            except SystemExit as e:
                print(f"   reactivation attempt failed: {str(e)[:120]}", flush=True)
        else:
            print("*** WF-2 DID NOT REACTIVATE - ACTIVATE IT MANUALLY ***", flush=True)

after_wf = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after_wf["nodes"]}
ac = after_wf["connections"]
problems = []
if OLD_CLAIM in an["Dedupe"]["parameters"]["jsCode"]:
    problems.append("Dedupe still claims at decision time")
if "__dedupe_key" not in an["Dedupe"]["parameters"]["jsCode"]:
    problems.append("Dedupe no longer emits __dedupe_key")
for name, aft, _, _ in NEW_NODES:
    if name not in an:
        problems.append(f"{name} missing")
    elif not any(c["node"] == name
                 for b in (ac.get(aft) or {}).get("main") or [] for c in (b or [])):
        problems.append(f"{name} not wired after {aft}")
for site in INLINE_SITES:
    if "__dedupe_key" not in an[site]["parameters"]["jsCode"]:
        problems.append(f"{site} does not claim")
if "__dedupe_key" in an.get("Ops Warn Unknown Event", {}).get("parameters", {}).get("jsCode", ""):
    problems.append("Ops Warn Unknown Event claims (must not)")
if after_wf.get("active") is not was:
    problems.append(f"active={after_wf.get('active')} (was {was})")
if len(after_wf["nodes"]) != wf_nodes_before + len([n for n, *_ in NEW_NODES
                                                    if n not in existing]):
    problems.append(f"node count {len(after_wf['nodes'])} unexpected")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after_wf.get('active')} versionId={after_wf.get('versionId')} "
      f"nodes={len(after_wf['nodes'])}")

# Marine's event (exec 14966) is the case that proved the defect. Report whether its key is still
# claimed - do NOT release it here: releasing causes WF-2R to replay, which sends a real forward,
# and the OOO was already corrected by hand earlier today. That is Nik's call, not a side effect.
sd = ((after_wf.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
mk = None
try:
    det = n8n("/api/v1/executions/14966?includeData=true")
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    mk = rd["Dedupe"][0]["data"]["main"][0][0]["json"].get("__dedupe_key")
except SystemExit as e:
    print(f"\n(Marine key lookup skipped: {str(e)[:90]})")
except Exception:
    pass
print(f"\nMarine (exec 14966) dedupe key: {mk!r}")
print(f"  still claimed in wf2_seen: {mk in sd if mk else 'unknown'}   "
      f"(wf2_seen entries: {len(sd)})")
print("  NOT released here - releasing triggers a WF-2R replay = a real forward. Nik's word.")
sys.exit(1 if problems else 0)
