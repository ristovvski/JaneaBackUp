#!/usr/bin/env python3
"""#18 - WF-1 alert gate: suppress on DELIVERY, not on decision, and not on labels.

NOT a port of WF-2's fix - WF-1 already has a registry (`__alerted_v1`, keyed by lead/person/
LinkedIn identity + campaign). Read the node first; its two real defects are different:

  1. LABEL-BASED SECONDARY SUPPRESSION (`responded_label`). '3. Responded' is written by Make, by
     Zaps, by our backfills and by humans - it was never a delivery receipt. 1,713 leads carried it
     before today's repairs, so any of them could be silenced by a writer that is not us.
  2. CLAIM AT DECISION TIME (line 58: `reg[key] = ...` immediately before `should = true`). If
     `M7 Critical Slack` then fails, the lead is burned forever - the same consequence that hid
     WF-2's 25 failed posts for eleven days.

Fix, code bodies only - NO graph change:
  * `M7 Alert Gate` stops reading labels and stops writing the registry.
  * `M7 Labels Compute` (Code, downstream of BOTH the alert and suppressed paths via M7 IF Patch)
    writes the claim, and only when Slack returned ok === true.
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

NEW_GATE = r"""
// W1.0.15 identity, W1.0.17 semantics: ONE alert per lead, suppressed on DELIVERY.
// Two things changed 2026-08-11:
//   * the '3. Responded' LABEL no longer suppresses. Labels are written by Make, Zaps, backfills
//     and humans - never a delivery receipt. 1,713 leads carried it, so any writer could silence us.
//   * the registry is NO LONGER written here. Claiming at decision time means a failed Slack post
//     burns the lead's only alert forever. `M7 Labels Compute` writes it on ok:true.
const CFG = $('CONFIG').item.json;
const b = $json;                                  // M7 Build output (carries alert_text)
const n = $('Normalize').item.json;
const sd = $getWorkflowStaticData('global');
const reg = sd.__alerted_v1 = sd.__alerted_v1 || {};

const camp = String((n.campaign && (n.campaign.id ?? n.campaign.name)) ?? 'nocamp');
const li = (n.lead && (n.lead.member_id || n.lead.public_id || n.lead.li_url)) || null;
const who = b.lead_id ? ('L' + b.lead_id)
          : (b.person_id ? ('P' + b.person_id)
          : (li ? ('M' + li) : null));
const key = who ? (who + '|' + camp) : null;

const now = Date.now();
let pruned = 0;
for (const k of Object.keys(reg)) {
  const t = Date.parse(reg[k]);
  if (Number.isFinite(t) && (now - t) > 90 * 86400000) { delete reg[k]; pruned++; }
}

let should, reason;
if (!key) {
  // no stable identity: a first reply must never be lost, so it alerts. Named, because this is the
  // only path that can still duplicate.
  should = true; reason = 'no_identity';
} else if (reg[key]) {
  should = false; reason = 'already_delivered';
} else {
  should = true; reason = 'first_alert';
}
return [{ json: { ...b, __alert_key: key, __should_alert: should, __alert_reason: reason,
                  __alert_registry_size: Object.keys(reg).length, __alert_pruned: pruned } }];
"""

CLAIM = r"""
// Records alert DELIVERY. Runs on BOTH branches (M7 Critical Slack and M7 Alert Suppressed both
// flow here through M7 IF Patch), so the try/catch is what distinguishes them: on the suppressed
// path `M7 Critical Slack` never ran and the lookup throws. The registry must never be written
// from the gate's DECISION - that is what burns a lead when a post fails.
try {
  const __s = $('M7 Critical Slack').item.json;
  if (__s && __s.ok === true) {
    const __k = $('M7 Alert Gate').item.json.__alert_key;
    if (__k) {
      const __sd = $getWorkflowStaticData('global');
      (__sd.__alerted_v1 = __sd.__alerted_v1 || {})[__k] = new Date().toISOString();
    }
  }
} catch (e) { /* alert not sent on this path */ }
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

# ---------------- statics: EXECUTE the gate body, assert decisions and that it writes nothing
tmp = os.path.join(HERE, "_wf1gate.js")
# NOTE the key shape: the gate builds who = 'L' + lead_id, so lead_id "1" -> key "L1|c".
# A first fixture passed lead_id "L1" and produced "LL1|c", missing the registry entry and
# reporting a false pass-through. The fixture must speak the gate's own key grammar.
cases = [
    ("virgin lead -> alert", {}, "1", True, "first_alert"),
    ("already DELIVERED -> suppress", {"L1|c": "2026-08-01T00:00:00Z"}, "1", False,
     "already_delivered"),
    ("other lead delivered -> still alert", {"L9|c": "2026-08-01T00:00:00Z"}, "1", True,
     "first_alert"),
    ("no identity -> fail open", {}, None, True, "no_identity"),
]
for label, reg0, lead, want_alert, want_reason in cases:
    js = f"""
const __sd = {{ __alerted_v1: {json.dumps(reg0)} }};
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => ({{ item: {{ json: nm === 'CONFIG'
  ? {{ labels: {{ responded: 'R' }}, fields: {{ lead_campaign: 'F' }} }}
  : {{ campaign: {{ id: 'c' }}, lead: {{}} }} }} }});
const $json = {{ lead_id: {json.dumps(lead)}, person_id: null }};
const __before = JSON.stringify(__sd.__alerted_v1);
const __out = (() => {{{NEW_GATE}}})();
const __after = JSON.stringify(__sd.__alerted_v1);
console.log(JSON.stringify({{ a: __out[0].json.__should_alert,
  r: __out[0].json.__alert_reason, wrote: __before !== __after }}));
"""
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-200:]}")
        os.remove(tmp); sys.exit(1)
    got = json.loads(p.stdout.strip())
    ok = (got["a"] is want_alert and got["r"] == want_reason and got["wrote"] is False)
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: alert={got['a']} reason={got['r']} "
          f"gate_wrote_registry={got['wrote']} (must be False)")
    if not ok:
        os.remove(tmp); sys.exit(1)
os.remove(tmp)

wf = n8n(f"/api/v1/workflows/{WF1}")
nodes = {n["name"]: n for n in wf["nodes"]}
gate, comp = nodes["M7 Alert Gate"], nodes["M7 Labels Compute"]
changes = []
if "already_delivered" not in gate["parameters"]["jsCode"]:
    gate["parameters"]["jsCode"] = NEW_GATE.strip()
    changes.append("M7 Alert Gate -> no label suppression, no registry write")
if "__alerted_v1" not in comp["parameters"]["jsCode"]:
    comp["parameters"]["jsCode"] = ("const __items = (() => {\n"
                                    + comp["parameters"]["jsCode"] + "\n})();\n"
                                    + CLAIM + "\nreturn __items;")
    changes.append("M7 Labels Compute -> claims on Slack ok:true only")

print("\n--- planned ---")
for c in changes:
    print("  -", c)
if not changes:
    print("  (already applied)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
open(os.path.join(HERE, f"wf1_backup_before_gatefix_{stamp}.json"), "w",
     encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF1}"), indent=2,
                                        ensure_ascii=False))
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF1}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF1}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF1}")
an = {x["name"]: x for x in after["nodes"]}
problems = []
if "already_delivered" not in an["M7 Alert Gate"]["parameters"]["jsCode"]:
    problems.append("gate not updated")
if "responded_label" in an["M7 Alert Gate"]["parameters"]["jsCode"]:
    problems.append("label suppression still present")
if "__alerted_v1" not in an["M7 Labels Compute"]["parameters"]["jsCode"]:
    problems.append("M7 Labels Compute does not claim")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
sys.exit(1 if problems else 0)
