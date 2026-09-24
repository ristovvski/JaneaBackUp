#!/usr/bin/env python3
"""DIAGNOSIS ONLY - how did a third-party reply enter WF-2, and who was the real campaign lead?

Melisa's case: 19:39 alert for pii-10d2dcec@example.invalid (HumanX 2026, via mario@) - a person who
was never a campaign lead, replying on someone else's thread.

Questions, answered from the payload rather than reasoned about:
  1. which Smartlead event type carried it
  2. does the payload DISTINGUISH the campaign lead's address from the actual sender? i.e. is there
     a field pair we can compare, or does Smartlead collapse both into one "lead" identity?
  3. who was the ORIGINAL lead on that thread
  4. what did WF-2 do with it - which person/lead did it resolve, and did it write anything

No writes. No changes. The fix comes after Nik sees this.
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
TARGET = "pii-10d2dcec@example.invalid"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
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


print("1. FIND THE EXECUTION")
ids, cursor = [], None
while True:
    q = {"workflowId": WF2, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor or len(ids) > 300:
        break
hit = None
for e in ids:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    blob = json.dumps(rd)[:400000]
    if TARGET.lower() in blob.lower():
        hit = (e, rd)
        break
if not hit:
    raise SystemExit(f"no WF-2 execution mentioning {TARGET} in the last {len(ids)} executions")
e, rd = hit
print(f"   exec {e['id']}  {e.get('startedAt')}  status={e.get('status')}")


def o(nm):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception:
        return None


print("\n2. RAW WEBHOOK PAYLOAD - what Smartlead actually sent")
wh = o("Webhook") or {}
body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
print(f"   event_type      : {body.get('event_type')!r}")
print(f"   campaign_id     : {body.get('campaign_id')}  {str(body.get('campaign_name'))[:50]!r}")
print(f"   sequence_number : {body.get('sequence_number')}")
print(f"   ALL keys        : {sorted(body.keys())}")
print("\n   every field containing an @ address:")
for k, v in sorted(body.items()):
    if isinstance(v, str) and "@" in v and len(v) < 200:
        flag = "   <-- THE THIRD PARTY" if TARGET.lower() in v.lower() else ""
        print(f"      {k:<28} {v!r}{flag}")
    elif isinstance(v, dict):
        for k2, v2 in v.items():
            if isinstance(v2, str) and "@" in v2 and len(v2) < 200:
                flag = "   <-- THE THIRD PARTY" if TARGET.lower() in v2.lower() else ""
                print(f"      {k}.{k2:<24} {v2!r}{flag}")

print("\n3. WHAT WF-2 MADE OF IT")
nm = o("Normalize") or {}
L = nm.get("lead") or {}
print(f"   Normalize.lead.email : {L.get('email')!r}")
print(f"   Normalize.event      : {nm.get('event')!r}")
print(f"   reply_category       : {nm.get('reply_category')!r}")
print(f"   sl_lead_id           : {nm.get('sl_lead_id')!r}")
for n2 in ("R Person Pick", "Lead Resolve", "First Reply Gate", "Reply Alert",
           "SL Forward Email"):
    j = o(n2)
    if j is None:
        print(f"   {n2:<20}: did not run")
        continue
    if n2 == "R Person Pick":
        print(f"   {n2:<20}: person_id={j.get('__person_id')} found={j.get('__person_found')} "
              f"candidates={j.get('__person_candidates')}")
    elif n2 == "Lead Resolve":
        print(f"   {n2:<20}: lead={str(j.get('__lead_id'))[:8]} how={j.get('__lead_how')!r} "
              f"no_lead={j.get('__no_lead')}")
    elif n2 == "First Reply Gate":
        print(f"   {n2:<20}: should={j.get('__should_alert')} reason={j.get('__alert_reason')!r}")
    elif n2 == "Reply Alert":
        print(f"   {n2:<20}: ok={j.get('ok')} channel={j.get('channel')}")
    else:
        print(f"   {n2:<20}: RAN")

print("\n4. WHO WAS THE ORIGINAL CAMPAIGN LEAD ON THIS THREAD?")
cid = body.get("campaign_id")
sid = nm.get("sl_lead_id") or body.get("sl_email_lead_id")
print(f"   campaign={cid} smartlead lead id={sid}")
if cid and sid:
    hist = (sl(f"/campaigns/{cid}/leads/{sid}/message-history") or {}).get("history") or []
    print(f"   message-history entries: {len(hist)}")
    for h in hist[-6:]:
        who = h.get("from") or h.get("to") or "?"
        print(f"      {h.get('time')} {str(h.get('type')):<8} from/to={str(who)[:46]!r} "
              f"subj={str(h.get('subject'))[:40]!r}")
    st = sl("/leads/", {"email": TARGET})
    print(f"\n   is the THIRD PARTY a Smartlead lead at all? "
          f"{'YES id=' + str(st.get('id')) if isinstance(st, dict) and st.get('id') else 'NO'}")

print("\n5. IS THE THIRD PARTY IN THE CRM?")
s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
       f"term={urllib.parse.quote(TARGET)}")
items = ((s or {}).get("data") or {}).get("items") or []
print(f"   pipedrive persons matching {TARGET}: {len(items)}")
for it in items:
    p = it.get("item") or {}
    print(f"      id={p.get('id')} name={p.get('name')!r}")
print("\n   => the proposed rule needs BOTH: sender != campaign lead email AND sender not in CRM")
