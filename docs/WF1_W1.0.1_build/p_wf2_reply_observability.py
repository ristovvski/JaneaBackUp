#!/usr/bin/env python3
"""#27 item 1 — the observability pair. This is the open 9b.0b gap: since 2026-08-13 WF-2 has been
making identity decisions (suppress / flag / forward-drop) with NO line anywhere explaining them.
Behaviourally correct, not observable.

+2 nodes as a NON-BLOCKING TEE off First Reply Gate (the WF-1 'Event Marker Warn' pattern):
  IF Reply Class Notable   - true for anything that is not a plain verified lead reply
  Reply Class Telemetry    - one line to #gtm-telemetry, onError continueRegularOutput

The tee is a SECOND branch on the gate's existing output, so the alert path is untouched: if Slack
is down, telemetry fails and the reply still gets processed. A blocking observability node would
make watching the system a way to break it.

+ the reply activity note now carries Smartlead's own category (Normalize already resolves it via
category_map), so the CRM card shows what the provider thought, next to what we decided.

NOTE the class vocabulary changed TODAY: 'ambiguous' no longer suppresses (Nik, 9b.0f correction),
it alerts flagged. So the line reports the DECISION, not just the class - otherwise it would still
read as if ambiguous were being silenced.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
TELEMETRY = "C0BQM1X9ZUY"

NOTABLE = ("={{ (() => { const g = $json || {};"
           " const c = String(g.__reply_class || 'lead');"
           " return c !== 'lead' || g.__ooo === true; })() }}")

TEXT = ("={{ (() => {"
        " const g = $json || {};"
        " const n = (() => { try { return $('Normalize').item.json || {}; } catch (e) { return {}; } })();"
        " const esc = (v) => String(v == null ? '' : v)"
        "   .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');"
        " const c = String(g.__reply_class || 'lead');"
        " const icon = g.__ooo ? '\\ud83c\\udf34' :"
        "   (c === 'third_party' ? '\\ud83d\\udd07' :"
        "   (c === 'ambiguous' ? '\\u2753' : (c === 'alias' ? '\\ud83d\\udd00' : '\\ud83e\\udded')));"
        " const decision = g.__should_alert === true"
        "   ? ('ALERTED' + (g.__identity_unverified ? ' (identity unverified)' : ''))"
        "   : ('no alert \\u00b7 ' + String(g.__alert_reason || 'unknown'));"
        " const who = esc((n.lead || {}).full_name || (n.lead || {}).email || 'unknown');"
        " const from = n.__reply_from && n.__reply_from !== (n.lead || {}).email"
        "   ? (' \\u00b7 written by ' + esc(n.__reply_from)) : '';"
        " const cat = n.reply_category ? (' \\u00b7 Smartlead: ' + esc(n.reply_category)) : '';"
        " const rec = n.__identity_reconstructed ? ' \\u00b7 replayed envelope' : '';"
        " return icon + ' reply class *' + c + '* \\u00b7 ' + who + from"
        "   + ' \\u00b7 ' + esc(n.campaign_name) + ' \\u2014 ' + decision + cat + rec; })() }}")

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if attempt < 4:
            time.sleep(8)
            return n8n(path, method, body, attempt + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.setdefault("connections", {})

if "IF Reply Class Notable" in N:
    sys.exit("telemetry pair already present - nothing to do")

# CONFIG: telemetry channel key
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
if not cfg.get("slack_channel_telemetry"):
    cfg["slack_channel_telemetry"] = TELEMETRY
    N["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
    print(f"CONFIG.slack_channel_telemetry = {TELEMETRY}")
else:
    print(f"CONFIG.slack_channel_telemetry already {cfg['slack_channel_telemetry']}")

gx, gy = N["First Reply Gate"]["position"]
wf["nodes"].append({
    "parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "combinator": "and",
        "conditions": [{"id": "obs-notable-0001", "leftValue": NOTABLE, "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}]}, "options": {}},
    "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [gx + 160, gy + 320],
    "id": "obs-if-replyclass-0001", "name": "IF Reply Class Notable"})
wf["nodes"].append({
    "parameters": {"select": "channel",
                   "channelId": {"__rl": True, "mode": "id",
                                 "value": "={{ $('CONFIG').item.json.slack_channel_telemetry }}"},
                   "text": TEXT,
                   "otherOptions": {"unfurl_links": False, "unfurl_media": False}},
    "type": "n8n-nodes-base.slack", "typeVersion": 2.3, "position": [gx + 400, gy + 320],
    "id": "obs-slack-replyclass-0001", "name": "Reply Class Telemetry",
    "credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}},
    # observability must never be able to break the path it observes
    "onError": "continueRegularOutput"})

gate_out = C.setdefault("First Reply Gate", {}).setdefault("main", [[]])
if not gate_out:
    gate_out.append([])
gate_out[0].append({"node": "IF Reply Class Notable", "type": "main", "index": 0})
C["IF Reply Class Notable"] = {"main": [[{"node": "Reply Class Telemetry", "type": "main",
                                          "index": 0}], []]}

# the activity note carries Smartlead's own category
js = N["Body Reply Activity"]["parameters"]["jsCode"]
OLD = "if (ctx('__summary', 'Classify Parse')) noteParts.push('— ' + ctx('__summary', 'Classify Parse'));"
NEW = (OLD + "\n"
       "// Smartlead's OWN category, next to whatever we decided - so the card shows the provider's\n"
       "// read rather than only ours. Normalize already resolves ids to names via category_map.\n"
       "if (n.reply_category) noteParts.push('Smartlead category: ' + n.reply_category);\n"
       "// identity, when it is not simply the lead speaking (9b.0i)\n"
       "if (n.__reply_class && n.__reply_class !== 'lead') {\n"
       "  noteParts.push('Identity: ' + n.__reply_class\n"
       "    + (n.__reply_from ? (' - written by ' + n.__reply_from) : '')\n"
       "    + (n.__identity_reconstructed ? ' (replayed envelope, sender not recorded)' : ''));\n"
       "}")
if OLD not in js:
    sys.exit("Body Reply Activity note block not found verbatim - refusing to patch blind")
N["Body Reply Activity"]["parameters"]["jsCode"] = js.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- statics
print("\n--- statics: IF condition + telemetry text ---")
ok = True


def run(expr, gate, norm):
    body = expr.strip()[4:-3].strip()
    src = f"""
const G = {json.dumps(gate)};
const NORM = {json.dumps(norm)};
const $json = G;
const $ = (nm) => {{ if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
                     throw new Error('absent ' + nm); }};
console.log(JSON.stringify({{ v: ({body}) }}));
"""
    tmp = os.path.join(HERE, "_obs.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:280]
    return json.loads(p.stdout.strip().splitlines()[-1])["v"], None


NORM_BASE = {"campaign_name": "AI4", "lead": {"email": "pii-362de426@example.invalid",
                                              "full_name": "Person-7267ff83"},
             "reply_category": "Interested"}
CASES = [
    ("plain verified lead reply -> NOT notable (no telemetry spam)",
     {"__reply_class": "lead", "__should_alert": True}, NORM_BASE, False, None),
    ("third_party -> notable, line must say it was silenced",
     {"__reply_class": "third_party", "__should_alert": False,
      "__alert_reason": "suppressed_third_party"},
     dict(NORM_BASE, __reply_from="pii-10d2dcec@example.invalid"), True, "no alert"),
    ("ambiguous -> notable, and must read as ALERTED, not silenced",
     {"__reply_class": "ambiguous", "__should_alert": True, "__identity_unverified": True},
     dict(NORM_BASE, __identity_reconstructed=True), True, "ALERTED (identity unverified)"),
    ("alias -> notable", {"__reply_class": "alias", "__should_alert": True},
     dict(NORM_BASE, __reply_from="pii-5d21e635@example.invalid"), True, "alias"),
    ("OOO -> notable even though class is lead",
     {"__reply_class": "lead", "__ooo": True, "__should_alert": False,
      "__alert_reason": "ooo_no_alert"}, NORM_BASE, True, "ooo_no_alert"),
]
for label, gate, norm, want_notable, want_sub in CASES:
    got, err = run(NOTABLE, gate, norm)
    if err:
        print(f"  [FAIL] {label}: {err}")
        ok = False
        continue
    good = got is want_notable
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  notable={got}")
    if want_sub:
        txt, err2 = run(TEXT, gate, norm)
        if err2:
            print(f"         [FAIL] text: {err2}")
            ok = False
            continue
        good2 = want_sub in txt
        ok = good2 and ok
        print(f"         [{'ok ' if good2 else 'FAIL'}] {txt[:150]}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
print(f"\nplanned: +2 nodes (tee off First Reply Gate, non-blocking), "
      f"activity note gains Smartlead category + identity line")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_obs_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in ("IF Reply Class Notable", "Reply Class Telemetry"):
    if nm not in AN:
        problems.append(f"{nm} missing")
if AN.get("Reply Class Telemetry", {}).get("onError") != "continueRegularOutput":
    problems.append("telemetry Slack node is BLOCKING - it could break the reply path")
outs = [c.get("node") for grp in (AC.get("First Reply Gate") or {}).get("main", [])
        for c in (grp or [])]
if "IF Reply Class Notable" not in outs or "IF Should Alert" not in outs:
    problems.append(f"gate fan-out wrong: {outs}")
if "Smartlead category" not in AN["Body Reply Activity"]["parameters"]["jsCode"]:
    problems.append("activity note not patched")
if len(after["nodes"]) != len(ORIG["nodes"]) + 2:
    problems.append(f"node count {len(after['nodes'])} != {len(ORIG['nodes'])}+2")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}  gate fan-out={outs}")
