#!/usr/bin/env python3
"""P0-1 HOTFIX - restore the `alert_text` declaration in Body Reply Alert.

WHAT I BROKE: the category-removal edit filtered out every line containing 'catTxt'. Line 27 was
    const alert_text = '...' + who + paren + catTxt + ' · ' + esc(n.campaign_name)
so the DECLARATION went with it, leaving lines 28-29 as orphaned - but syntactically VALID -
continuation expressions, and `alert_text` undefined at the return. Runtime ReferenceError.
`Body Reply Alert` has no onError, so it kills the whole execution: every reply after 15:10:44Z
was destroyed, not merely un-alerted.

WHY IT SHIPPED: my check asserted `'catTxt' not in jsCode` (true) and the deploy did a syntax
check (passes - the orphans are valid JS). Neither executed the node body.

THE STATIC NOW EXECUTES THE BODY and asserts alert_text is a non-empty string. A syntax check is
not evidence; this class shipped clean twice today on syntax checks alone.
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

BROKEN_HEAD = "  + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink"
FIXED_HEAD = ("const alert_text = '💬 ' + who + paren + ' · ' + esc(n.campaign_name)\n"
              "  + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def execute_body(js, label):
    """THE point of this script: run the node body with realistic stubs and assert the output."""
    harness = f"""
const $ = (nm) => ({{ item: {{ json:
  nm === 'CONFIG' ? {{ pipedrive_base: 'https://pd', sl_inbox_base: 'https://sl?m=' }}
: nm === 'Normalize' ? {{ lead: {{ full_name: 'Test Person', email: 'pii-cb236733@example.invalid', title: 'VP',
                                   company: 'Acme' }},
                          campaign_name: '[Events] X', sender_inbox: 'pii-6f267dd7@example.invalid',
                          sl_app_url: null, sl_lead_map_id: 42 }}
: {{}} }} }});
const $json = {{ __lead_id: 'L1', __person_id: 9 }};
const __out = (() => {{
{js}
}})();
const t = __out && __out[0] && __out[0].json ? __out[0].json.alert_text : undefined;
if (typeof t !== 'string' || t.length === 0) {{
  console.error('ASSERT FAILED: alert_text is ' + JSON.stringify(t));
  process.exit(3);
}}
console.log(t.slice(0, 120));
"""
    tmp = os.path.join(HERE, "_p01check.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip().splitlines()[-1][:160]}")
        return False, None
    print(f"  [ok]   {label}: {(p.stdout or '').strip()[:110]}")
    return True, (p.stdout or "").strip()


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
node = next(n for n in wf["nodes"] if n["name"] == "Body Reply Alert")
js = node["parameters"]["jsCode"]

print("--- proving the CURRENT node is broken (the static that was missing) ---")
cur_ok, _ = execute_body(js, "current live code")
if cur_ok:
    print("current code already produces alert_text - nothing to fix")
    sys.exit(0)

if BROKEN_HEAD not in js:
    print("REFUSING: the expected broken line was not found verbatim; re-read before patching")
    sys.exit(2)
fixed = js.replace(BROKEN_HEAD, FIXED_HEAD, 1)

print("\n--- proving the FIXED node works ---")
fix_ok, rendered = execute_body(fixed, "patched code")
if not fix_ok:
    print("REFUSING: the patch does not produce a non-empty alert_text")
    sys.exit(1)
if "catTxt" in fixed or "Classify Parse" in fixed:
    print("REFUSING: the category line must stay removed (it fires before classification)")
    sys.exit(1)

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
open(os.path.join(HERE, f"wf2_backup_before_P01_{stamp}.json"), "w",
     encoding="utf-8").write(json.dumps(wf, indent=2, ensure_ascii=False))
node["parameters"]["jsCode"] = fixed
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
an = next(n for n in after["nodes"] if n["name"] == "Body Reply Alert")
live_ok, _ = execute_body(an["parameters"]["jsCode"], "LIVE code after deploy")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
problems = []
if not live_ok:
    problems.append("live code still does not produce alert_text")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"WRITE_MODE={acfg.get('WRITE_MODE')}")
sys.exit(1 if problems else 0)
