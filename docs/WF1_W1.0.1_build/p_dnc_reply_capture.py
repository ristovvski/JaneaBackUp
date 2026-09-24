#!/usr/bin/env python3
"""DNC REPLY CAPTURE — inline in BOTH receivers. Nik's ruling: everyone who replies to any of our
campaigns goes to DNC active.

I raised that `reply_dnc` maps to entry_type `negative_reply` and therefore suppresses positive
repliers too; Nik reaffirmed the rule in full. Building it as ruled.

REASON MAPPING (all legal per the ledger's REASON_TO_ENTRY_TYPE):
  explicit stop phrase        -> unsubscribe  -> explicit_opt_out   (permanent)
  any other genuine reply     -> reply_dnc    -> negative_reply     (DNC active)
With date_precision 'unknown', reasonExpiryOverride sets expires_at = null, i.e. permanent.

NEVER WRITTEN - the existing locks, reused, not re-derived:
  * OOO / auto-reply   - WF-2's __isOOO (Smartlead reply_category)
  * bounces            - event type BOUNCED never reaches the reply path
  * non-campaign chats - WF-1's __manual_thread / WF-2's campaign attribution

FIRE-AND-FORGET: the Execute Workflow node is onError:continueRegularOutput on a dedicated branch,
so a ledger hiccup can never fail or delay a reply, an alert, or a CRM write.

WF-1 AND reply_category: the ledger THROWS on reply_dnc without one, and HeyReach has no categories
at all (verified: no classifier, no sentiment, Normalize emits none). WF-1 therefore sends
`linkedin_reply_uncategorised` - deliberately named so these rows are findable later, rather than
borrowing a provider category that does not exist.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = "RolYGL3J2CNg6Yp3"

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, att=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


STOP_RX = (r"/\b(unsubscribe|opt[\s-]?out|remove me|take me off|stop (?:emailing|contacting|messaging)"
           r"|do not (?:contact|email|message)|don'?t (?:contact|email|message) me"
           r"|no longer (?:interested|wish)|please stop)\b/i")

# ---------------------------------------------------------------- WF-2
WF2_GATE = ("={{ (() => { const g = $json || {};"
            " const n = (() => { try { return $('Normalize').item.json || {}; }"
            "   catch (e) { return {}; } })();"
            " const camp = n.campaign_id ?? n.campaign_name ?? null;"
            " const isReply = String(n.event || '').toUpperCase() === 'REPLIED';"
            " const ooo = g.__ooo === true;"
            " return !!camp && isReply && !ooo; })() }}")

WF2_BUILD = r"""
// DNC capture, email side. Nik 2026-09-03: everyone who replies to any of our campaigns goes to
// DNC active. An explicit stop phrase is the stronger, permanent tier.
const n = $('Normalize').item.json;
const ctxj = (() => { try { return $('Merge Reply Ctx').item.json || {}; }
                      catch (e) { return {}; } })();
const L = n.lead || {};
const body = String((n.reply && (n.reply.body || n.reply.text)) || '');
const STOP = """ + STOP_RX + r""";
const isStop = STOP.test(body);
// reply_dnc REQUIRES a category - Smartlead supplies one; fall back to a named placeholder rather
// than throwing, so a categoryless reply still registers and stays findable.
const cat = n.reply_category || 'email_reply_uncategorised';
return [{ json: {
  linkedin_url: L.linkedin || null,
  email: L.email || null,
  full_name: L.full_name || null,
  external_id: n.sl_lead_id || n.sl_email_lead_id || null,
  pipedrive_person_id: ctxj.__person_id ?? null,
  reason: isStop ? 'unsubscribe' : 'reply_dnc',
  reply_category: cat,
  source: 'campaign_reply',
  source_ref: n.campaign_name || String(n.campaign_id || ''),
  date_precision: 'unknown',
  expiry_review_pending: false,
  correlation_id: 'wf2_reply:' + (n.campaign_id || 'nocamp') + ':' +
                  (L.email || ctxj.__person_id || 'unknown'),
  __dnc_stop_phrase: isStop
} }];
"""

# ---------------------------------------------------------------- WF-1
WF1_GATE = ("={{ (() => { const b = $json || {};"
            " const n = (() => { try { return $('Normalize').item.json || {}; }"
            "   catch (e) { return {}; } })();"
            " const ev = String(n.event || '').toLowerCase();"
            " const isReply = ev.indexOf('reply_received') !== -1;"
            " return isReply && b.__manual_thread !== true; })() }}")

WF1_BUILD = r"""
// DNC capture, LinkedIn side. Same ruling, same tiers. HeyReach has no reply categories at all -
// no classifier, no sentiment, nothing in Normalize - and the ledger throws on reply_dnc without
// one, so we send a NAMED placeholder rather than borrowing a category that does not exist.
const n = $('Normalize').item.json;
const b = (() => { try { return $('M7 Alert Key').item.json || {}; }
                   catch (e) { return $json || {}; } })();
const L = n.lead || {};
const msgs = Array.isArray(n.msgs) ? n.msgs : [];
const lastIn = msgs.filter(m => m && m.is_reply).slice(-1)[0] || {};
const text = String(lastIn.message || '');
const STOP = """ + STOP_RX + r""";
const isStop = STOP.test(text);
return [{ json: {
  linkedin_url: L.url || L.profile_url || null,
  email: L.email_address || L.enriched_email || L.custom_email || null,
  full_name: L.full_name || null,
  external_id: L.id || null,
  pipedrive_person_id: b.person_id ?? null,
  reason: isStop ? 'unsubscribe' : 'reply_dnc',
  reply_category: 'linkedin_reply_uncategorised',
  source: 'campaign_reply',
  source_ref: (n.campaign && n.campaign.name) || String((n.campaign && n.campaign.id) || ''),
  date_precision: 'unknown',
  expiry_review_pending: false,
  correlation_id: 'wf1_reply:' + ((n.campaign && n.campaign.id) || 'nocamp') + ':' +
                  (L.slug || L.id || b.person_id || 'unknown'),
  __dnc_stop_phrase: isStop
} }];
"""


def call_node(name, pos, nid):
    return {"parameters": {"source": "database",
                           "workflowId": {"__rl": True, "mode": "id", "value": LEDGER},
                           "mode": "each", "options": {}},
            "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
            "position": pos, "id": nid, "name": name,
            "onError": "continueRegularOutput", "alwaysOutputData": True}


def if_node(name, expr, pos, nid):
    return {"parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "combinator": "and",
        "conditions": [{"id": nid + "-c", "leftValue": expr, "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}]}, "options": {}},
        "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos, "id": nid, "name": name}


plans = []
# ---- WF-2
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
N2 = {n["name"]: n for n in wf2["nodes"]}
if "DNC Reply Gate" in N2:
    print("WF-2 already has the capture branch")
else:
    C2 = wf2.setdefault("connections", {})
    gx, gy = N2["First Reply Gate"]["position"]
    new2 = [if_node("DNC Reply Gate", WF2_GATE, [gx + 160, gy + 520], "wf2-dncgate"),
            {"parameters": {"jsCode": WF2_BUILD}, "type": "n8n-nodes-base.code",
             "typeVersion": 2, "position": [gx + 340, gy + 520], "id": "wf2-dncbuild",
             "name": "DNC Build Input"},
            call_node("DNC Upsert Call", [gx + 520, gy + 520], "wf2-dnccall")]
    wf2["nodes"].extend(new2)
    N2.update({x["name"]: x for x in new2})
    fg = C2.setdefault("First Reply Gate", {}).setdefault("main", [[]])
    if not fg:
        fg.append([])
    fg[0].append({"node": "DNC Reply Gate", "type": "main", "index": 0})
    C2["DNC Reply Gate"] = {"main": [[{"node": "DNC Build Input", "type": "main", "index": 0}], []]}
    C2["DNC Build Input"] = {"main": [[{"node": "DNC Upsert Call", "type": "main", "index": 0}]]}
    plans.append(("jp7rum9Z0YDJkQWv", wf2, [x["name"] for x in new2], "First Reply Gate"))

# ---- WF-1
wf1 = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N1 = {n["name"]: n for n in wf1["nodes"]}
if "M7 DNC Reply Gate" in N1:
    print("WF-1 already has the capture branch")
else:
    C1 = wf1.setdefault("connections", {})
    kx, ky = N1["M7 Alert Key"]["position"]
    new1 = [if_node("M7 DNC Reply Gate", WF1_GATE, [kx, ky + 420], "wf1-dncgate"),
            {"parameters": {"jsCode": WF1_BUILD}, "type": "n8n-nodes-base.code",
             "typeVersion": 2, "position": [kx + 180, ky + 420], "id": "wf1-dncbuild",
             "name": "M7 DNC Build Input"},
            call_node("M7 DNC Upsert Call", [kx + 360, ky + 420], "wf1-dnccall")]
    wf1["nodes"].extend(new1)
    N1.update({x["name"]: x for x in new1})
    ak = C1.setdefault("M7 Alert Key", {}).setdefault("main", [[]])
    if not ak:
        ak.append([])
    ak[0].append({"node": "M7 DNC Reply Gate", "type": "main", "index": 0})
    C1["M7 DNC Reply Gate"] = {"main": [[{"node": "M7 DNC Build Input", "type": "main",
                                          "index": 0}], []]}
    C1["M7 DNC Build Input"] = {"main": [[{"node": "M7 DNC Upsert Call", "type": "main",
                                           "index": 0}]]}
    plans.append(("2jdjKM2NJr473GdA", wf1, [x["name"] for x in new1], "M7 Alert Key"))

print(f"prepared: {[(p[0], p[2]) for p in plans]}")

# ---------------------------------------------------------------- statics
print("\n--- statics (class level) ---")
ok = True


def run(js_or_expr, harness, pick, is_expr=False):
    body = (js_or_expr.strip()[4:-3].strip() if is_expr else js_or_expr)
    src = harness + ("\nconsole.log(JSON.stringify({v: (" + body + ")}));"
                     if is_expr else
                     "\nconst OUT = (() => {\n" + body + "\n})();\nconsole.log(JSON.stringify("
                     + pick + "));")
    tmp = os.path.join(HERE, "_dnc.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:280]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


def H2(norm, gate=None, merge=None):
    return f"""
const NORM = {json.dumps(norm)};
const $json = {json.dumps(gate or {})};
const $ = (nm) => {{
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Merge Reply Ctx') return {{ item: {{ json: {json.dumps(merge or {})} }} }};
  throw new Error('absent ' + nm);
}};
"""


def H1(norm, akey=None):
    return f"""
const NORM = {json.dumps(norm)};
const $json = {json.dumps(akey or {})};
const $ = (nm) => {{
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'M7 Alert Key') return {{ item: {{ json: {json.dumps(akey or {})} }} }};
  throw new Error('absent ' + nm);
}};
"""


N2_REPLY = {"event": "REPLIED", "campaign_id": 3868449, "campaign_name": "FinovateFall",
            "reply_category": "Interested", "reply": {"body": "Sounds great, let's meet"},
            "lead": {"email": "pii-da50e332@example.invalid", "full_name": "A B", "linkedin": None}}
N2_STOP = dict(N2_REPLY, reply={"body": "Please unsubscribe me from this list"})
N2_OOO = dict(N2_REPLY, reply_category="Out Of Office")
N2_BOUNCE = dict(N2_REPLY, event="BOUNCED")
N2_MANUAL = dict(N2_REPLY, campaign_id=None, campaign_name=None)
N1_REPLY = {"event": "every_message_reply_received", "campaign": {"id": 572715, "name": "Fin LI"},
            "msgs": [{"message": "happy to chat", "is_reply": True}],
            "lead": {"url": "https://linkedin.com/in/x", "full_name": "X Y", "slug": "x"}}

CASES2 = [
    ("WF-2 campaign reply -> WRITES", H2(N2_REPLY, {"__ooo": False}), True),
    ("WF-2 OOO -> never written", H2(N2_OOO, {"__ooo": True}), False),
    ("WF-2 bounce -> never written", H2(N2_BOUNCE, {"__ooo": False}), False),
    ("WF-2 non-campaign -> never written", H2(N2_MANUAL, {"__ooo": False}), False),
]
for label, h, want in CASES2:
    got, err = run(WF2_GATE, h, None, is_expr=True)
    good = (not err) and got["v"] is want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  -> {got['v'] if not err else err}")

got, err = run(WF2_BUILD, H2(N2_REPLY, {"__ooo": False}, {"__person_id": 42}),
               "{r: OUT[0].json.reason, c: OUT[0].json.reply_category,"
               " k: OUT[0].json.correlation_id, p: OUT[0].json.pipedrive_person_id}")
good = (not err and got["r"] == "reply_dnc" and got["c"] == "Interested" and got["p"] == 42)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-2 normal reply -> reason=reply_dnc (DNC active)  "
      f"{got if not err else err}")

got, err = run(WF2_BUILD, H2(N2_STOP, {"__ooo": False}), "{r: OUT[0].json.reason}")
good = (not err and got["r"] == "unsubscribe")
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-2 explicit stop -> reason=unsubscribe (permanent)")

got, err = run(WF1_GATE, H1(N1_REPLY, {"__manual_thread": False}), None, is_expr=True)
good = (not err and got["v"] is True)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-1 campaign reply -> WRITES")
got, err = run(WF1_GATE, H1(N1_REPLY, {"__manual_thread": True}), None, is_expr=True)
good = (not err and got["v"] is False)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-1 manual chat -> never written (regression)")
got, err = run(WF1_GATE, H1(dict(N1_REPLY, event="connection_request_sent"),
                            {"__manual_thread": False}), None, is_expr=True)
good = (not err and got["v"] is False)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-1 non-reply event -> never written")

got, err = run(WF1_BUILD, H1(N1_REPLY, {"__manual_thread": False, "person_id": 99}),
               "{r: OUT[0].json.reason, c: OUT[0].json.reply_category,"
               " k: OUT[0].json.correlation_id}")
good = (not err and got["r"] == "reply_dnc"
        and got["c"] == "linkedin_reply_uncategorised")
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] WF-1 reply -> reply_dnc + named placeholder category  "
       f"{got if not err else err}")

# idempotency: the same reply twice must produce the SAME correlation_id
g1, _ = run(WF1_BUILD, H1(N1_REPLY, {"person_id": 99}), "OUT[0].json.correlation_id")
g2, _ = run(WF1_BUILD, H1(N1_REPLY, {"person_id": 99}), "OUT[0].json.correlation_id")
good = g1 == g2 and g1 is not None
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] same reply twice -> identical correlation_id ({g1})")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wid, wfobj, names, parent in plans:
    with open(os.path.join(HERE, f"backup_before_dnc_{wid}_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(n8n(f"/api/v1/workflows/{wid}"), indent=2, ensure_ascii=False))
    stripped_keys(wfobj)
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(wfobj))
    after = n8n(f"/api/v1/workflows/{wid}")
    AN = {n["name"]: n for n in after["nodes"]}
    AC = after.get("connections") or {}
    probs = [nm for nm in names if nm not in AN]
    call = [nm for nm in names if "Upsert Call" in nm][0]
    if AN.get(call, {}).get("onError") != "continueRegularOutput":
        probs.append(f"{call} is BLOCKING")
    outs = [c.get("node") for g in (AC.get(parent) or {}).get("main", []) for c in (g or [])]
    if names[0] not in outs:
        probs.append(f"{parent} not teed: {outs}")
    print(f"\n{wid}: {'CLEAN' if not probs else 'PROBLEMS ' + str(probs)}  "
          f"version={after.get('versionId')} nodes={len(after['nodes'])}")
    print(f"   {parent} -> {outs}")
