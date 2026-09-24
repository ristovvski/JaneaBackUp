#!/usr/bin/env python3
"""Item 3 - route routine reconciler ticks to #gtm-telemetry; Nik's channel keeps only the notable.

SCOPE FILTER FIRST (section 9b.0g, written tonight after a discovery script walked through an
ownership boundary): this touches EXACTLY two workflow ids, asserted below. No discovery.

Routing: the Report node's channel becomes an expression - notable ? ops_channel : telemetry_channel.
No new nodes, no branch. `Summary` computes __notable:
  * __failed  > 0                      - a replay was REJECTED
  * __dropped > previous cycle's        - cap-drop GROWING cycle-over-cycle (a shrinking backlog is
                                          not news; a growing one is)
  * WF-2S: __campaign_overflow > 0 · WF-2R: __truncated - coverage gaps, always notable

The previous drop count lives in staticData. That is normally the race-prone pattern, but these
reconcilers are schedule-driven every 15 minutes with 3-16s runtimes and were measured non-
overlapping, so there is no concurrent writer here. Noting it because the assumption is load-bearing.

Alarm nodes (Idle Warn, Ops Warn *) are deliberately NOT rerouted - they are alarms, not ticks.
"""
import argparse, copy, json, os, re, ssl, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
TELEMETRY = "C0BQM1X9ZUY"
# ---- the allowlist. Anything discovered outside this set is an ABORT, not a warning.
ALLOW = {"6Y92ryBwYoy6z0Jx": ("WF-2S", "WF-2S Report", "__campaign_overflow > 0"),
         "U8Bb7Pdq7S6nzYPa": ("WF-2R", "WF-2R Report", "__truncated === true")}

NOTABLE_TMPL = """
// TELEMETRY ROUTING: routine ticks go to #gtm-telemetry, only the notable reach Nik's channel.
// "cap dropped N" is only news when it GROWS - a shrinking backlog is the system working.
const __sdN = $getWorkflowStaticData('global');
const __prevDrop = Number(__sdN.__prev_dropped ?? 0);
const __curDrop = Number((__items[0] && __items[0].json && __items[0].json.__dropped) ?? 0);
__sdN.__prev_dropped = __curDrop;
const __j0 = (__items[0] && __items[0].json) || {};
const __notable = (Number(__j0.__failed ?? 0) > 0)
  || (__curDrop > __prevDrop)
  || (__EXTRA__);
"""


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


def add_telemetry_to_config(node):
    """CONFIG is a Set node holding a JSON blob; add telemetry_channel beside ops_channel."""
    params = node.get("parameters") or {}
    for key, val in list(params.items()):
        if isinstance(val, str) and "ops_channel" in val:
            try:
                obj = json.loads(val)
            except Exception:
                continue
            if obj.get("telemetry_channel") == TELEMETRY:
                return False
            obj["telemetry_channel"] = TELEMETRY
            params[key] = json.dumps(obj, ensure_ascii=False, indent=2)
            return True
    raise SystemExit("CONFIG: could not find a JSON field containing ops_channel")


def run_static(js, label, prev, cur, failed, extra_true, want):
    harness = f"""
const __sd = {{ __prev_dropped: {prev} }};
const $getWorkflowStaticData = () => __sd;
const __items = [{{ json: {{ __dropped: {cur}, __failed: {failed},
                             __campaign_overflow: {1 if extra_true else 0},
                             __truncated: {str(extra_true).lower()} }} }}];
{js}
console.log(JSON.stringify({{ notable: __notable, stored: __sd.__prev_dropped }}));
"""
    tmp = os.path.join(HERE, "_tele_case.js")
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

plans, ok = {}, True
for wid, (tag, report, extra) in ALLOW.items():
    wf = n8n(f"/api/v1/workflows/{wid}")
    if wf.get("id") != wid:
        raise SystemExit(f"id mismatch: asked {wid}, got {wf.get('id')} - aborting")
    orig = copy.deepcopy(wf)
    N = {n["name"]: n for n in wf["nodes"]}
    if report not in N:
        raise SystemExit(f"{tag}: {report} missing")

    summ = N["Summary"]["parameters"]["jsCode"]
    notable_js = NOTABLE_TMPL.replace("__EXTRA__", f"__j0.{extra}")
    if "__notable" in summ:
        new_summ = summ
        changed_summ = False
    else:
        # IIFE-wrap, the pattern used all day: the original body is untouched inside the closure,
        # so its return shape does not matter. A first attempt regex-matched a single-line trailing
        # `return`, and WF-2S's Summary ends with a MULTI-LINE return (the alert_text map) - the
        # anchor guard caught it rather than letting a mangled body through.
        new_summ = ("const __items = (() => {\n" + summ + "\n})();\n" + notable_js
                    + "\nreturn (__items || []).map(it => ({ json: { ...(it.json || {}),"
                      " __notable: __notable } }));\n")
        changed_summ = True

    print(f"\n--- statics: {tag} notability ---")
    ok = run_static(notable_js, f"{tag}: clean cycle -> NOT notable",
                    5, 3, 0, False, {"notable": False, "stored": 3}) and ok
    ok = run_static(notable_js, f"{tag}: a rejected replay -> notable",
                    0, 0, 2, False, {"notable": True}) and ok
    ok = run_static(notable_js, f"{tag}: cap-drop GROWING -> notable",
                    4, 9, 0, False, {"notable": True, "stored": 9}) and ok
    ok = run_static(notable_js, f"{tag}: cap-drop shrinking -> NOT notable",
                    9, 4, 0, False, {"notable": False, "stored": 4}) and ok
    ok = run_static(notable_js, f"{tag}: coverage gap ({extra}) -> notable",
                    0, 0, 0, True, {"notable": True}) and ok

    cfg_changed = add_telemetry_to_config(N["CONFIG"])
    rep = N[report]
    ch = ((rep["parameters"].get("channelId") or {}).get("value") or "")
    want_ch = ("={{ $json.__notable === true ? $('CONFIG').first().json.ops_channel"
               " : $('CONFIG').first().json.telemetry_channel }}")
    ch_changed = ch != want_ch
    if ch_changed:
        rep["parameters"]["channelId"]["value"] = want_ch
    N["Summary"]["parameters"]["jsCode"] = new_summ
    plans[wid] = {"wf": wf, "orig": orig, "tag": tag, "report": report,
                  "changes": [x for x, c in (("CONFIG telemetry_channel", cfg_changed),
                                             ("Summary __notable", changed_summ),
                                             (f"{report} channel expression", ch_changed)) if c]}

print("\n--- planned (allowlist enforced: only these two ids) ---")
for wid, p in plans.items():
    print(f"  {p['tag']} ({wid}): {p['changes'] or 'no change'}")
if not ok:
    sys.exit(1)
if not any(p["changes"] for p in plans.values()):
    print("(already applied)")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
problems = []
for wid, p in plans.items():
    if not p["changes"]:
        continue
    with open(os.path.join(HERE, f"{p['tag']}_backup_before_telemetry_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(p["orig"], indent=2, ensure_ascii=False))
    stripped_keys(p["wf"])
    n8n(f"/api/v1/workflows/{wid}", None, "PUT", put_body(p["wf"]))
    after = n8n(f"/api/v1/workflows/{wid}")
    AN = {n["name"]: n for n in after["nodes"]}
    chv = ((AN[p["report"]]["parameters"].get("channelId") or {}).get("value") or "")
    if "telemetry_channel" not in chv or "__notable" not in chv:
        problems.append(f"{p['tag']}: report channel expression not applied")
    if "__notable" not in AN["Summary"]["parameters"]["jsCode"]:
        problems.append(f"{p['tag']}: Summary lacks __notable")
    if TELEMETRY not in json.dumps(AN["CONFIG"]["parameters"]):
        problems.append(f"{p['tag']}: CONFIG lacks the telemetry channel id")
    if after.get("active") is not p["orig"].get("active"):
        problems.append(f"{p['tag']}: active={after.get('active')}")
    if len(after["nodes"]) != len(p["orig"]["nodes"]):
        problems.append(f"{p['tag']}: node count changed")
    print(f"  {p['tag']} versionId={after.get('versionId')} active={after.get('active')} "
          f"nodes={len(after['nodes'])}")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for x in problems:
    print("  -", x)
print(f"\nnext tick lands in {TELEMETRY} unless the cycle is notable. Confirm on the wire.")
sys.exit(1 if problems else 0)
