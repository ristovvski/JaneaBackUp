#!/usr/bin/env python3
"""#27 item 1c — the Test-owner note.

CONFIG carries `forward_owner_map.Test -> melisa@janeasystems.com`: a TEST owner pointing at a real
person's inbox. If any sending inbox ever maps to the owner name 'Test', we forward a prospect's
reply into Melisa's real mailbox as though it were routine. That is silent today.

Forward Resolve is DOWNSTREAM of First Reply Gate, so the reply-class telemetry tee cannot see it -
checked, not assumed. So this gets its own non-blocking tee off Forward Resolve, same shape:
  IF Forward Owner Test  -> true when the resolved owner name is 'Test' (or the target is the
                            configured test address), whatever the inbox map says
  Forward Test Telemetry -> one line to #gtm-telemetry, onError continueRegularOutput

Deliberately NOT a block on the forward: section 9e says the forward is the delivery mechanism for
696 of 710 mailboxes. Telemetry observes; it does not get to stop a reply reaching a human.
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

COND = ("={{ (() => { const j = $json || {};"
        " const owner = String(j.__forward_owner || '').trim().toLowerCase();"
        " if (owner === 'test') return true;"
        " const cfg = (() => { try { return $('CONFIG').item.json || {}; } catch (e) { return {}; } })();"
        " const testAddr = String(((cfg.forward_owner_map || {}).Test) || '').trim().toLowerCase();"
        " const to = String(j.__forward_to || '').trim().toLowerCase();"
        " return !!(testAddr && to && to === testAddr); })() }}")

TEXT = ("={{ (() => {"
        " const j = $json || {};"
        " const n = (() => { try { return $('Normalize').item.json || {}; } catch (e) { return {}; } })();"
        " const esc = (v) => String(v == null ? '' : v)"
        "   .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');"
        " return '\\ud83e\\uddea *TEST forward owner used* \\u2014 a real prospect reply is being"
        " forwarded to the Test address. inbox `' + esc(n.sender_inbox) + '` \\u2192 owner `'"
        " + esc(j.__forward_owner) + '` \\u2192 ' + esc(j.__forward_to)"
        " + ' \\u00b7 lead ' + esc((n.lead || {}).email)"
        " + ' \\u00b7 ' + esc(n.campaign_name)"
        " + '. CONFIG.forward_owner_map.Test points at a real inbox \\u2014 if this fires in"
        " production, fix the map, not the alert.'; })() }}")

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
if "IF Forward Owner Test" in N:
    sys.exit("already present - nothing to do")

cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
test_addr = (cfg.get("forward_owner_map") or {}).get("Test")
print(f"CONFIG.forward_owner_map.Test = {test_addr!r}")
if not test_addr:
    print("  (no Test owner configured right now - the guard still ships, it is the map that moves)")

fx, fy = N["Forward Resolve"]["position"]
wf["nodes"].append({
    "parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "combinator": "and",
        "conditions": [{"id": "obs-testowner-0001", "leftValue": COND, "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}]}, "options": {}},
    "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [fx + 160, fy + 300],
    "id": "obs-if-testowner-0001", "name": "IF Forward Owner Test"})
wf["nodes"].append({
    "parameters": {"select": "channel",
                   "channelId": {"__rl": True, "mode": "id",
                                 "value": "={{ $('CONFIG').item.json.slack_channel_telemetry }}"},
                   "text": TEXT,
                   "otherOptions": {"unfurl_links": False, "unfurl_media": False}},
    "type": "n8n-nodes-base.slack", "typeVersion": 2.3, "position": [fx + 400, fy + 300],
    "id": "obs-slack-testowner-0001", "name": "Forward Test Telemetry",
    "credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}},
    "onError": "continueRegularOutput"})

out = C.setdefault("Forward Resolve", {}).setdefault("main", [[]])
if not out:
    out.append([])
out[0].append({"node": "IF Forward Owner Test", "type": "main", "index": 0})
C["IF Forward Owner Test"] = {"main": [[{"node": "Forward Test Telemetry", "type": "main",
                                         "index": 0}], []]}

print("\n--- statics ---")
ok = True


def run(expr, j, cfgj):
    body = expr.strip()[4:-3].strip()
    src = f"""
const J = {json.dumps(j)};
const CFG = {json.dumps(cfgj)};
const NORM = {json.dumps({"sender_inbox": "pii-fd989748@example.invalid", "campaign_name": "AI4",
                          "lead": {"email": "pii-787bcb74@example.invalid"}})};
const $json = J;
const $ = (nm) => {{ if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
                     if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
                     throw new Error('absent ' + nm); }};
console.log(JSON.stringify({{ v: ({body}) }}));
"""
    tmp = os.path.join(HERE, "_testowner.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:280]
    return json.loads(p.stdout.strip().splitlines()[-1])["v"], None


CFGJ = {"forward_owner_map": {"Test": "melisa@janeasystems.com",
                              "Mario": "mario@janeasystems.com"}}
CASES = [
    ("owner name is 'Test' -> fires",
     {"__forward_owner": "Test", "__forward_to": "melisa@janeasystems.com"}, True),
    ("owner name differs but target IS the Test address -> still fires",
     {"__forward_owner": "Melisa", "__forward_to": "melisa@janeasystems.com"}, True),
    ("normal owner -> silent (no telemetry spam on every forward)",
     {"__forward_owner": "Mario", "__forward_to": "mario@janeasystems.com"}, False),
    ("owner miss, default target -> silent (that has its own warn)",
     {"__forward_owner": None, "__forward_to": "default@janeasystems.com"}, False),
    ("empty resolve -> silent, never fire on absence",
     {"__forward_owner": "", "__forward_to": ""}, False),
]
for label, j, want in CASES:
    got, err = run(COND, j, CFGJ)
    if err:
        print(f"  [FAIL] {label}: {err}")
        ok = False
        continue
    good = got is want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  fires={got}")
txt, err = run(TEXT, {"__forward_owner": "Test", "__forward_to": "melisa@janeasystems.com"}, CFGJ)
if err:
    print(f"  [FAIL] text: {err}")
    ok = False
else:
    good = "TEST forward owner used" in txt
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {txt[:170]}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_testowner_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in ("IF Forward Owner Test", "Forward Test Telemetry"):
    if nm not in AN:
        problems.append(f"{nm} missing")
if AN.get("Forward Test Telemetry", {}).get("onError") != "continueRegularOutput":
    problems.append("telemetry node is BLOCKING the forward path")
outs = [c.get("node") for grp in (AC.get("Forward Resolve") or {}).get("main", [])
        for c in (grp or [])]
if "IF Forward Owner Test" not in outs:
    problems.append(f"tee not wired: {outs}")
if len(outs) < 2:
    problems.append(f"Forward Resolve lost its original downstream: {outs}")
if len(after["nodes"]) != len(ORIG["nodes"]) + 2:
    problems.append(f"node count {len(after['nodes'])} != {len(ORIG['nodes'])}+2")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} nodes={len(after['nodes'])} "
      f"Forward Resolve fan-out={outs}")
