#!/usr/bin/env python3
"""Surgical replay of richard.spitz's lost SENT event, rebuilt from SMARTLEAD'S OWN RECORD.

Why not the crashed execution's payload: that payload is OUR copy of what arrived, and the whole
reason we are here is that our copies have been unreliable tonight. Provider record is the source;
the crashed payload is used ONLY as a shape template and a cross-check, and every value taken from
it rather than the wire is reported.

He is 915 minutes old - far outside WF-2S's 180-minute lookback - so no reconciler will ever reach
him. One POST, then grade the whole chain on the wire.

Expected outcome: person/lead resolved or created, dedupe key claimed, and ZERO forwards (forwarding
is a REPLIED-branch behaviour; a SENT event must not forward). The F-key and no-lead guards are live,
so this also exercises them.
"""
import argparse, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
EXEC = "15949"
EMAIL = "pii-0ddf11ef@example.invalid"
STATS_ID = "f826809a-8ac1-4ac2-a846-708a73e26f2d"


def n8n(p, q=None, method="GET", body=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   n8n read failed: {str(e)[:110]}")
        return None


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   smartlead read failed: {str(e)[:110]}")
        return None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


ap = argparse.ArgumentParser()
ap.add_argument("--post", action="store_true")
a = ap.parse_args()

# ---------------------------------------------------------------- 1. our copy (template only)
print("1. CROSS-CHECK SOURCE - the crashed execution's stored payload (shape template only)")
det = n8n(f"/api/v1/executions/{EXEC}", {"includeData": "true"})
rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
try:
    wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
    ours = wh.get("body") if isinstance(wh.get("body"), dict) else wh
except Exception:
    sys.exit("cannot read the crashed execution's webhook body - stopping")
print(f"   keys: {sorted(ours.keys())}")
print(f"   campaign_id={ours.get('campaign_id')} stats_id={ours.get('stats_id')} "
      f"event_type={ours.get('event_type')!r} sequence_number={ours.get('sequence_number')}")
cid = ours.get("campaign_id")

# ---------------------------------------------------------------- 2. provider truth
print("\n2. PROVIDER TRUTH - Smartlead's own record for this campaign+lead")
lead = sl(f"/leads/", {"email": EMAIL}) or {}
sl_lead_id = lead.get("id")
print(f"   /leads?email -> id={sl_lead_id} name={lead.get('first_name')} {lead.get('last_name')}")
hist = (sl(f"/campaigns/{cid}/leads/{sl_lead_id}/message-history") or {}).get("history") or []
sents = [h for h in hist if str(h.get("type", "")).upper() == "SENT"]
print(f"   message-history entries: {len(hist)}   SENT: {len(sents)}")
match = None
for h in sents:
    if str(h.get("stats_id")) == STATS_ID:
        match = h
        break
if not match and sents:
    match = sents[-1]
    print("   !! no stats_id match; falling back to the most recent SENT - REPORTED, not hidden")
if not match:
    sys.exit("Smartlead has no SENT record for this lead - refusing to fabricate an event")
print(f"   matched SENT: stats_id={match.get('stats_id')} time={match.get('time')} "
      f"subject={str(match.get('subject'))[:50]!r}")

# ---------------------------------------------------------------- 3. reconstruct
print("\n3. RECONSTRUCTED PAYLOAD (provider values; template fields marked)")
body = dict(ours)
from_wire, from_template = [], []
for k, v in (("stats_id", match.get("stats_id")),
             ("time_sent", match.get("time")),
             ("subject", match.get("subject")),
             ("email_subject", match.get("subject"))):
    if v is not None and k in body:
        body[k] = v
        from_wire.append(k)
for k in body:
    if k not in from_wire:
        from_template.append(k)
print(f"   from WIRE     : {from_wire}")
print(f"   from TEMPLATE : {sorted(from_template)}")
print(f"\n   payload:\n{json.dumps(body, ensure_ascii=False, indent=2)[:1200]}")

ws = n8n(f"/api/v1/workflows/{WF2S}")
cfgn = next((n for n in (ws or {}).get("nodes", []) if n["name"] == "CONFIG"), None)
raw = json.dumps((cfgn or {}).get("parameters") or {})
import re
m = re.search(r'\\"wf2_webhook\\":\s*\\"([^\\"]+)\\"', raw)
hook = m.group(1) if m else None
print(f"\n   target webhook: {hook}")
if not hook:
    sys.exit("could not read wf2_webhook from WF-2S CONFIG")

w2 = n8n(f"/api/v1/workflows/{WF2}")
seen_before = ((w2 or {}).get("staticData") or {}).get("global", {}).get("wf2_seen") or {}
print(f"   wf2_seen before: {len(seen_before)}")
if not a.post:
    print("\n--post not given: nothing sent.")
    sys.exit(0)

# ---------------------------------------------------------------- 4. one POST
print("\n4. POSTING (one request)")
req = urllib.request.Request(hook, method="POST", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=120, context=ctx) as x:
        print(f"   HTTP {x.status}  {x.read()[:160].decode('utf-8', 'replace')}")
except urllib.error.HTTPError as e:
    print(f"   HTTP {e.code}  {e.read()[:200].decode('utf-8', 'replace')}")
    sys.exit("webhook rejected the replay")
print("   NOTE: a 200 here is the webhook ACK only - node #2 answers before any work.")
print("   That is exactly the flaw that orphaned him; grading below uses the CHAIN, not this 200.")
time.sleep(75)

# ---------------------------------------------------------------- 5. grade the chain
print("\n5. GRADED CHAIN")
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 15})
mine = None
for e in (ex or {}).get("data") or []:
    d2 = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    r2 = (((d2 or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        nm = r2["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    if str((nm.get("lead") or {}).get("email", "")).lower() == EMAIL:
        mine = (e, r2)
        break
if not mine:
    print("   NO EXECUTION FOUND for the replay - NOT a pass")
    sys.exit(1)
e, r2 = mine
dk = None
try:
    dk = r2["Dedupe"][0]["data"]["main"][0][0]["json"].get("__dedupe_key")
except Exception:
    pass
w2b = n8n(f"/api/v1/workflows/{WF2}")
seen_after = ((w2b or {}).get("staticData") or {}).get("global", {}).get("wf2_seen") or {}
person = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
            f"term={urllib.parse.quote(EMAIL)}")
items = ((person or {}).get("data") or {}).get("items") or []
pid = (items[0].get("item") or {}).get("id") if items else None
leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or [] if pid else []
fwd = "SL Forward Email" in r2

checks = {
    "execution succeeded": e.get("status") == "success",
    "dedupe key claimed (P0-1b)": bool(dk) and dk in seen_after,
    "person resolved/created in Pipedrive": pid is not None,
    "lead present for that person": len(leads) > 0,
    "ZERO forwards (SENT must not forward)": fwd is False,
}
print(f"   exec {e['id']} {e.get('startedAt')} status={e.get('status')}")
print(f"   dedupe_key={dk}")
print(f"   wf2_seen {len(seen_before)} -> {len(seen_after)}")
print(f"   pipedrive person={pid} leads={[str(l.get('id'))[:8] for l in leads]}")
for k, v in checks.items():
    print(f"   [{'OK ' if v else 'RED'}] {k}")
print(f"\nSPITZ RECOVERY: {'PASS' if all(checks.values()) else 'FAIL'}")
sys.exit(0 if all(checks.values()) else 1)
