#!/usr/bin/env python3
"""FLIP BLOCKER FIX - canonicalise the timestamp component of WF-2's Dedupe key.

THE DEFECT (measured live 2026-08-07, both executions in shadow so nothing was written):
  exec 14110  genuine Smartlead webhook  key REPLIED|3686187|4306240392|2026-08-07T08:11:00+00:00
  exec 14116  WF-2R reconciler replay    key REPLIED|3686187|4306240392|2026-08-07T08:11:00.000Z
Same event, same instant, two different STRINGS -> two different keys -> duplicate=False on the
second -> in WRITE_MODE=live that reply is forwarded twice and activity-logged twice.

Dedupe joins raw String(v) values, so it is comparing formatting, not time. Every source that
words a timestamp differently defeats it: Smartlead's webhook, leads-statistics history, WF-2S,
WF-2R, and anything added later.

THE FIX - one expression. Parse the timestamp and key on epoch milliseconds; fall back to the raw
string only when it is unparseable, so an odd payload degrades to today's behaviour rather than
collapsing every unparseable event onto one key.

Deliberately narrow: it touches the key's timestamp component only. Event, campaign_id and
sl_lead_id are untouched, the store name is untouched (so existing claims stay valid), and no
other node is modified.

  python patch_wf2_dedupe_canon.py            # show the diff, verify, write nothing
  python patch_wf2_dedupe_canon.py --deploy   # deactivate -> PUT -> activate -> re-read
"""
import argparse, json, os, ssl, sys, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"

OLD = ("const key = [n.event, n.campaign_id, n.sl_lead_id, n.timestamp]"
       ".map(v => String(v ?? '')).join('|');")
NEW = """// B-DEDUPE-TS (2026-08-07): this joined RAW strings, so it compared FORMATTING, not time.
// Proven live: the same reply arrived as '2026-08-07T08:11:00+00:00' from Smartlead's webhook and
// '2026-08-07T08:11:00.000Z' from the WF-2R replay - identical instant, two keys, duplicate=false.
// In live mode that is a double forward and a double activity. Key on epoch ms instead; an
// unparseable timestamp falls back to its raw string rather than collapsing onto a shared key.
const __ts = (() => { const p = Date.parse(n.timestamp ?? ''); \
return Number.isFinite(p) ? String(p) : String(n.timestamp ?? ''); })();
const key = [n.event, n.campaign_id, n.sl_lead_id, __ts].map(v => String(v ?? '')).join('|');"""


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
        raise


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
print(f"WF-2 live: versionId={wf.get('versionId')} nodes={len(wf['nodes'])} "
      f"active={wf.get('active')}")
ded = next(n for n in wf["nodes"] if n["name"] == "Dedupe")
js = ded["parameters"]["jsCode"]
if OLD not in js:
    if "__ts" in js:
        print("already patched - nothing to do")
        sys.exit(0)
    print("REFUSING: the expected Dedupe key line was not found verbatim. WF-2 has changed; "
          "re-read it before patching rather than forcing a replacement.")
    sys.exit(2)

patched = js.replace(OLD, NEW)
print("\n--- replacing ---")
print(OLD)
print("--- with ---")
print(NEW)

# local proof that the two observed key formats now collapse onto one key
import subprocess
harness = r"""
const mk = (ts) => { const n = { event:'REPLIED', campaign_id:3686187, sl_lead_id:'4306240392',
  timestamp: ts };
  const __ts = (() => { const p = Date.parse(n.timestamp ?? '');
    return Number.isFinite(p) ? String(p) : String(n.timestamp ?? ''); })();
  return [n.event, n.campaign_id, n.sl_lead_id, __ts].map(v => String(v ?? '')).join('|'); };
const a = mk('2026-08-07T08:11:00+00:00');       // genuine Smartlead webhook
const b = mk('2026-08-07T08:11:00.000Z');        // WF-2R replay
const c = mk('2026-08-07T08:12:00.000Z');        // a genuinely different reply
const d = mk('not-a-date');                      // unparseable -> raw fallback
console.log(JSON.stringify({ collapse: a === b, distinct: a !== c,
                             fallback: d.endsWith('not-a-date'), a, b }));
"""
p = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
print("\nkey-collapse check:", p.stdout.strip() or p.stderr.strip())
chk = json.loads(p.stdout.strip())
if not (chk["collapse"] and chk["distinct"] and chk["fallback"]):
    print("REFUSING: the patched expression does not behave correctly")
    sys.exit(1)
print("  collapse=True  distinct=True  fallback=True")

if not a.deploy:
    print("\n--deploy not given: nothing written. WF-2 is untouched.")
    sys.exit(0)

backup = f"wf2_backup_before_dedupe_canon_{int(datetime.now(timezone.utc).timestamp())}.json"
open(backup, "w", encoding="utf-8").write(json.dumps(wf, indent=2, ensure_ascii=False))
print(f"\nbackup: {backup}")
for n in wf["nodes"]:
    if n["name"] == "Dedupe":
        n["parameters"]["jsCode"] = patched
was_active = wf.get("active")
if was_active:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402
_dropped = stripped_keys(wf)
if _dropped:
    print(f"stripping UI-only settings keys the API rejects: {_dropped}")
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
if was_active:
    n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})
after = n8n(f"/api/v1/workflows/{WF2}")
live_ded = next(n for n in after["nodes"] if n["name"] == "Dedupe")["parameters"]["jsCode"]
ok = ("__ts" in live_ded) and (after.get("active") == was_active) \
    and len(after["nodes"]) == len(wf["nodes"])
print(f"\nlive verification: {'CLEAN' if ok else 'PROBLEM'}")
print(f"  active={after.get('active')} nodes={len(after['nodes'])} "
      f"versionId={after.get('versionId')}")
sys.exit(0 if ok else 1)
