#!/usr/bin/env python3
"""Gate fix (mark-after-delivery) + alert template cleanup, one deploy.

THREE changes:

1. `First Reply Gate` no longer suppresses on the '3. Responded' LABEL. Labels are written by
   Make, by Zaps, by our backfills and by humans - they were never a delivery receipt. Using them
   meant (a) any writer could silence our notifications and (b) a FAILED Slack post still burned
   the lead's one alert forever. Proven live 2026-08-10: exec 14922 decided should_alert=true,
   the post died with 'invalid syntax', the label was written anyway, and every later reply on
   that lead was suppressed as a repeat. Now: an own registry in staticData, keyed by lead.

2. `Classify Body` (the node that runs immediately after `Reply Alert`) records the delivery -
   and ONLY on `ok === true`. Its own logic is IIFE-wrapped and untouched.

3. `Body Reply Alert` drops the category line. The alert fires ~228ms BEFORE classification even
   starts (measured: Body Reply Alert 1786374243283, Classify Body 1786374243511), so the
   category can never be read there. Speed is the feature; removing the promise beats half-keeping
   it. chat.update remains an option if categories are ever wanted, never coupling.

TRADE-OFF, stated: staticData does not survive a workflow rebuild the way a CRM label does, so a
rebuild may let a previously-alerted lead alert once more. A duplicate alert is recoverable; a
silently suppressed one is not.
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

NEW_GATE = r"""
const CFG = $('CONFIG').item.json;
const n = (() => { try { return $('Normalize').item.json; } catch (e) { return {}; } })();
// DELIVERY-BASED suppression (2026-08-10). The old rule read the '3. Responded' LABEL, which is
// written by Make, Zaps, backfills and humans - never a delivery receipt. Two failures followed:
// any writer could silence our alerts, and a FAILED Slack post still burned the lead's single
// alert forever. This registry is set ONLY when Slack returns ok:true (see Classify Body).
const sd = $getWorkflowStaticData('global');
const reg = sd.__alert_delivered = (sd.__alert_delivered || {});
const nowSec = Math.floor(Date.now() / 1000);
const maxAge = Number(CFG.alert_registry_max_age_sec ?? 7776000);   // 90d, bounded memory
let pruned = 0;
for (const k of Object.keys(reg)) {
  if (nowSec - Number(reg[k]) > maxAge) { delete reg[k]; pruned++; }
}
const key = String($json.__lead_id ?? $json.__person_id ?? (n.lead && n.lead.email) ?? '');
const already = key ? Object.prototype.hasOwnProperty.call(reg, key) : false;
const alertEvery = !!(CFG.flags && CFG.flags.alert_every_reply === true);
// no key at all -> fail OPEN and alert; a missed notification is worse than a duplicate
const should = alertEvery ? true : (!key ? true : !already);
return [{ json: { ...$json, __should_alert: should, __alert_key: key,
  __alert_reason: alertEvery ? 'alert_every_reply'
    : (!key ? 'fail_open_no_key' : (already ? 'already_delivered' : 'first_reply')),
  __alert_pruned: pruned, __alert_registry_size: Object.keys(reg).length } }];
"""

RECORD_SNIPPET = r"""
// Records alert DELIVERY - and only delivery. Runs here because this node executes immediately
// after `Reply Alert`; the registry must never be set from the gate's decision, which is exactly
// how a failed post used to burn a lead's only alert.
try {
  const __r = $('Reply Alert').item.json;
  if (__r && __r.ok === true) {
    const __sd = $getWorkflowStaticData('global');
    const __reg = __sd.__alert_delivered = (__sd.__alert_delivered || {});
    const __k = String($('First Reply Gate').item.json.__alert_key || '');
    if (__k) __reg[__k] = Math.floor(Date.now() / 1000);
  }
} catch (e) { /* alert branch did not run in this execution */ }
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

# ---------------- local behavioural proof of the new gate
tmp = os.path.join(HERE, "_gatecheck.js")
cases = [
    ("virgin lead -> alert", {}, "L1", True, "first_reply"),
    ("already DELIVERED -> suppress", {"L1": 1786370000}, "L1", False, "already_delivered"),
    ("delivered for a DIFFERENT lead -> alert", {"L9": 1786370000}, "L1", True, "first_reply"),
    ("no key -> fail open", {}, "", True, "fail_open_no_key"),
]
for label, reg0, key, want_alert, want_reason in cases:
    js = f"""
const __sd = {{ __alert_delivered: {json.dumps(reg0)} }};
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => ({{ item: {{ json: nm === 'CONFIG'
  ? {{ flags: {{}}, alert_registry_max_age_sec: 7776000 }}
  : {{ lead: {{ email: '' }} }} }} }});
const $json = {{ __lead_id: {json.dumps(key) if key else 'null'} }};
const __out = (() => {{{NEW_GATE}}})();
console.log(JSON.stringify({{ a: __out[0].json.__should_alert,
                              r: __out[0].json.__alert_reason }}));
"""
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-200:]}")
        os.remove(tmp); sys.exit(1)
    got = json.loads(p.stdout.strip())
    ok = got["a"] is want_alert and got["r"] == want_reason
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: alert={got['a']} reason={got['r']}")
    if not ok:
        os.remove(tmp); sys.exit(1)
os.remove(tmp)

wf = n8n(f"/api/v1/workflows/{WF2}")
nodes = {n["name"]: n for n in wf["nodes"]}
gate, cbody, abody = nodes["First Reply Gate"], nodes["Classify Body"], nodes["Body Reply Alert"]

changes = []
if "__alert_delivered" not in gate["parameters"]["jsCode"]:
    gate["parameters"]["jsCode"] = NEW_GATE.strip()
    changes.append("First Reply Gate -> delivery registry (was label-based)")
if "__alert_delivered" not in cbody["parameters"]["jsCode"]:
    cbody["parameters"]["jsCode"] = (
        "const __items = (() => {\n" + cbody["parameters"]["jsCode"] + "\n})();\n"
        + RECORD_SNIPPET + "\nreturn __items;")
    changes.append("Classify Body -> records delivery on ok:true only")
if "catTxt" in abody["parameters"]["jsCode"]:
    js = abody["parameters"]["jsCode"]
    js = "\n".join(l for l in js.splitlines()
                   if "Classify Parse" not in l and "catTxt" not in l and "const cat =" not in l
                   and "catch (e) { return null; } })();" not in l)
    js = js.replace(" + catTxt", "")
    abody["parameters"]["jsCode"] = js
    changes.append("Body Reply Alert -> category line removed (fires before classification)")

print("\n--- planned ---")
for c in changes:
    print("  -", c)
if not changes:
    print("  (nothing to do)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
open(os.path.join(HERE, f"wf2_backup_before_gatefix_{stamp}.json"), "w",
     encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF2}"), indent=2,
                                        ensure_ascii=False))
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
acfg = json.loads(an["CONFIG"]["parameters"]["jsonOutput"])
problems = []
if "__alert_delivered" not in an["First Reply Gate"]["parameters"]["jsCode"]:
    problems.append("gate not converted")
if "__alert_delivered" not in an["Classify Body"]["parameters"]["jsCode"]:
    problems.append("Classify Body does not record delivery")
if "catTxt" in an["Body Reply Alert"]["parameters"]["jsCode"]:
    problems.append("category line still present")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])} WRITE_MODE={acfg.get('WRITE_MODE')}")
sys.exit(1 if problems else 0)
