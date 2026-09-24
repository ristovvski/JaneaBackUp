#!/usr/bin/env python3
"""Invert the WRITE_MODE watchdog: live is now the declared steady state, shadow is the anomaly.

BEFORE: 'WF-2 has been live for more than write_mode_max_hours - revert or confirm.' That policed a
temporary window. The flip made live permanent, so the alarm nagged every cycle forever and, worse,
said NOTHING about the condition that actually matters now.

AFTER: CONFIG declares `write_mode_expected` and the watchdog alarms whenever the live WRITE_MODE
disagrees with it. Consequences:
  * the 2h nag stops because the condition is FALSE, not because it was muted
  * a rollback to shadow becomes LOUD - today it is completely silent, and a silent rollback means
    replies are logged instead of written while every digest still looks busy
  * a future planned shadow window just sets write_mode_expected='shadow'; no code change
  * an UNREADABLE mode also alarms - a watchdog that cannot see must shout, not stay quiet

Node name and connections untouched: `__mode_overdue` remains the output key `IF Mode Overdue`
tests, so no connection surgery on a live workflow.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2S = "6Y92ryBwYoy6z0Jx"

NEW_EVAL = r"""
// WRITE_MODE watchdog, INVERTED 2026-08-10. Live is the declared steady state after the flip;
// shadow is now the anomaly. The old rule ('live for more than N hours') policed a temporary
// window that no longer exists - it nagged forever and stayed silent about the thing that now
// matters: someone quietly rolling back to shadow, which turns every CRM write into a log line
// while the digests still look busy.
const CFG = $('CONFIG').first().json;
const expected = String(CFG.write_mode_expected || 'live');
let mode = null;
try {
  const wf = $json;                                   // workflow JSON from 'WF-2 Mode Read'
  const cfgNode = (wf.nodes || []).find((n) => n.name === 'CONFIG');
  mode = JSON.parse(cfgNode.parameters.jsonOutput).WRITE_MODE;
} catch (e) { mode = null; }

const unreadable = (mode === null || mode === undefined);
const mismatch = !unreadable && String(mode) !== expected;
// a watchdog that cannot see must shout, not stay quiet
const overdue = unreadable || mismatch;

const alert_text = unreadable
  ? ('🚨 WF-2 WRITE_MODE could not be read from the n8n API. The write-mode watchdog is blind - '
     + 'treat as unverified, not as healthy.')
  : ('🚨 WF-2 WRITE_MODE is \'' + mode + '\' but the declared steady state is \'' + expected
     + '\'. Someone rolled back - replies are being LOGGED, not written to the CRM. '
     + 'Either restore live or update write_mode_expected.');

return [{ json: { __mode_overdue: overdue, __mode_actual: mode, __mode_expected: expected,
                  __mode_unreadable: unreadable, alert_text } }];
"""


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# ---- prove the new evaluator behaves, before touching anything
cases = [
    ("steady state (live == live)", "live", "live", False),
    ("rolled back to shadow", "shadow", "live", True),
    ("planned shadow window", "shadow", "shadow", False),
    ("unreadable mode", None, "live", True),
]
tmp = os.path.join(HERE, "_modecheck.js")
for label, actual, expected, want in cases:
    wf_json = ("{nodes:[{name:'CONFIG',parameters:{jsonOutput:JSON.stringify({WRITE_MODE:"
               + (f"'{actual}'" if actual else "undefined") + "})}}]}")
    js = ("const $ = () => ({ first: () => ({ json: { write_mode_expected: '"
          + expected + "' } }) });\nconst $json = " + wf_json + ";\n"
          + "const __r = (() => {" + NEW_EVAL + "})();\n"
          + "console.log(JSON.stringify({overdue:__r[0].json.__mode_overdue,"
          + "text:String(__r[0].json.alert_text).slice(0,60)}));")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-160:]}")
        os.remove(tmp)
        sys.exit(1)
    got = json.loads(p.stdout.strip())
    ok = got["overdue"] is want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: overdue={got['overdue']} (want {want})")
    if not ok:
        os.remove(tmp)
        sys.exit(1)
os.remove(tmp)

wf = n8n(f"/api/v1/workflows/{WF2S}")
cfg_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
evl = next(n for n in wf["nodes"] if n["name"] == "WF-2 Mode Eval")

print(f"\nCONFIG now: write_mode_max_hours={cfg.get('write_mode_max_hours')!r} "
      f"write_mode_expected={cfg.get('write_mode_expected')!r}")
cfg.pop("write_mode_max_hours", None)
cfg["write_mode_expected"] = "live"
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
evl["parameters"]["jsCode"] = NEW_EVAL.strip()
print("planned: delete write_mode_max_hours · set write_mode_expected='live' · "
      "replace WF-2 Mode Eval")

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
open(os.path.join(HERE, f"wf2s_backup_before_modeinvert_{stamp}.json"), "w",
     encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF2S}"), indent=2,
                                        ensure_ascii=False))
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2S}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2S}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF2S}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2S}")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
aevl = next(n for n in after["nodes"] if n["name"] == "WF-2 Mode Eval")["parameters"]["jsCode"]
problems = []
if "write_mode_max_hours" in acfg:
    problems.append("write_mode_max_hours still present")
if acfg.get("write_mode_expected") != "live":
    problems.append(f"write_mode_expected={acfg.get('write_mode_expected')!r}")
if "write_mode_expected" not in aevl:
    problems.append("WF-2 Mode Eval not replaced")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
print(f"  write_mode_expected={acfg.get('write_mode_expected')!r} "
      f"write_mode_max_hours={'absent' if 'write_mode_max_hours' not in acfg else 'STILL THERE'}")
sys.exit(1 if problems else 0)
