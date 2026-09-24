#!/usr/bin/env python3
"""FIX - WF-2 reply alerts have never posted. 25/25 executions returned 'invalid syntax'.

CAUSE: the Slack node's `text` is a 1,154-char IIFE containing backward `.item` lookups, nested
try/catch and unicode escapes - all inside an n8n EXPRESSION, where the expression parser rejects
it. WF-1's equivalent alert works because it does the opposite: it builds the string in a CODE
node and the Slack node reads `={{ $json.alert_text }}`.

FIX: same shape as WF-1. Move the text building into `Body Reply Alert` (a Code node, real JS) and
reduce the Slack node to `={{ $json.alert_text }}`. Nurture Alert gets the same treatment - it has
the identical construct and would fail the moment it fires.

WHY IT WAS INVISIBLE: onError=continueRegularOutput keeps the execution 'success', shadow mode
meant nobody looked for the post, and a check that asked 'did the node run' answered yes.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.error, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"

REPLY_BODY_JS = r"""
// Builds the reply alert text HERE, in a Code node, instead of inside the Slack node's expression.
// The previous design put a 1,154-char IIFE (backward .item lookups, nested try/catch, unicode
// escapes) into an n8n EXPRESSION, which the expression parser rejected: 25/25 executions returned
// 'invalid syntax' and no reply alert has ever reached Slack. WF-1's working alert uses exactly
// this shape - Code node builds the string, Slack node reads $json.alert_text.
const CFG = $('CONFIG').item.json;
const n = $('Normalize').item.json;
const esc = (v) => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const fromNode = (nm) => { try { return $(nm).item.json || {}; } catch (e) { return {}; } };
const L = $json.__lead_id ?? fromNode('Merge Reply Ctx').__lead_id
       ?? fromNode('Lead Resolve').__lead_id ?? null;
const P = $json.__person_id ?? fromNode('Merge Reply Ctx').__person_id
       ?? fromNode('R Person Pick').__person_id ?? null;
const base = CFG.pipedrive_base;
const who = esc(n.lead.full_name || n.lead.email);
const pos = n.lead.title ? esc(n.lead.title) : '';
const co = n.lead.company ? esc(n.lead.company) : '';
const paren = (pos || co) ? (' (' + [pos, co].filter(Boolean).join(' @ ') + ')') : '';
const link = L ? ('<' + base + '/leads/inbox/' + L + '|Open lead>')
               : (P ? ('no lead · <' + base + '/person/' + P + '|Open person>')
                    : 'no lead · not in CRM yet');
const slUrl = n.sl_app_url || (n.sl_lead_map_id ? (CFG.sl_inbox_base + n.sl_lead_map_id) : null);
const slLink = slUrl ? (' · <' + slUrl + '|Open in Smartlead>') : '';
const cat = (() => { try { return $('Classify Parse').item.json.__category || null; }
                     catch (e) { return null; } })();
const catTxt = cat ? (' · *' + esc(cat) + '*') : '';
const alert_text = '💬 ' + who + paren + catTxt + ' · ' + esc(n.campaign_name)
  + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink
  + ' · ✉️ ' + esc(n.lead.email);
return [{ json: { ...$json, alert_text, __body: { text: alert_text }, __skip: !alert_text,
  __intended: { node: 'Reply Alert', method: 'POST', url: 'slack:replies',
                body: { text: alert_text } } } }];
"""

NURTURE_BODY_JS = r"""
// Same fix as Body Reply Alert: build the string in JS, not in the Slack node's expression.
const n = $('Normalize').item.json;
const esc = (v) => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const alert_text = '💬 ' + esc(n.lead.full_name || n.lead.email) + ' · '
  + esc(n.campaign_name) + ' · ✉️ ' + esc(n.lead.email) + ' · nurture';
return [{ json: { ...$json, alert_text, __body: { text: alert_text }, __skip: !alert_text,
  __intended: { node: 'Nurture Alert', method: 'POST', url: 'slack:replies',
                body: { text: alert_text } } } }];
"""

PAIRS = [("Body Reply Alert", "Reply Alert", REPLY_BODY_JS),
         ("Body Nurture Alert", "Nurture Alert", NURTURE_BODY_JS)]


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        raise


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
names = {n["name"]: n for n in wf["nodes"]}
changed = []
for body_name, slack_name, js in PAIRS:
    b, s = names.get(body_name), names.get(slack_name)
    if not s:
        print(f"  {slack_name}: not found, skipping")
        continue
    if not b:
        print(f"  {body_name}: not found - cannot move the text out of the expression")
        continue
    cur = str((s.get("parameters") or {}).get("text") or "")
    if cur.strip() == "={{ $json.alert_text }}":
        print(f"  {slack_name}: already fixed")
    else:
        s["parameters"]["text"] = "={{ $json.alert_text }}"
        changed.append(f"{slack_name}.text -> $json.alert_text (was {len(cur)} chars of IIFE)")
    if "alert_text" not in ((b.get("parameters") or {}).get("jsCode") or ""):
        b["parameters"]["jsCode"] = js.strip()
        changed.append(f"{body_name} now builds alert_text")

print("\nplanned changes:")
for c in changed:
    print("  -", c)
if not changed:
    print("  (none)")
    sys.exit(0)

# local syntax proof - the whole bug was a string that did not parse
harness = REPLY_BODY_JS.replace("$('CONFIG').item.json", "({pipedrive_base:'https://p',sl_inbox_base:'https://s?m='})") \
    .replace("$('Normalize').item.json",
             "({lead:{full_name:'A B',email:'a@b.c',title:'VP',company:'Acme'},"
             "campaign_name:'[X] Y',sender_inbox:'pii-6f267dd7@example.invalid',sl_app_url:null,sl_lead_map_id:7})") \
    .replace("$json", "({__lead_id:'L1',__person_id:9})") \
    .replace("$('Classify Parse').item.json", "({__category:'Meeting Request'})") \
    .replace("$(nm).item.json", "({})")
harness = "const out = (() => {" + harness + "})(); console.log(out[0].json.alert_text);"
p = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
print(f"\nlocal render: {p.stdout.strip()[:200] or p.stderr.strip()[:300]}")
if p.returncode != 0:
    print("REFUSING: the replacement JS does not even parse locally")
    sys.exit(1)

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

backup = os.path.join(HERE, f"wf2_backup_before_alertfix_{int(datetime.now(timezone.utc).timestamp())}.json")
open(backup, "w", encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF2}"), indent=2,
                                                     ensure_ascii=False))
print(f"\nbackup: {backup}")
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
ok = (after.get("active") is was
      and str(an["Reply Alert"]["parameters"].get("text")).strip() == "={{ $json.alert_text }}"
      and "alert_text" in an["Body Reply Alert"]["parameters"]["jsCode"]
      and len(after["nodes"]) == len(wf["nodes"]))
acfg = json.loads(an["CONFIG"]["parameters"]["jsonOutput"])
print(f"\nlive verification: {'CLEAN' if ok else 'PROBLEM'}")
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
print(f"  Reply Alert.text = {an['Reply Alert']['parameters'].get('text')!r}")
print(f"  WRITE_MODE still: {acfg.get('WRITE_MODE')}")
sys.exit(0 if ok else 1)
