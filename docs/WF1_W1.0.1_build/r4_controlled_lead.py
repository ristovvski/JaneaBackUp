#!/usr/bin/env python3
"""R4 - prepare the controlled flip-gate reply.

WHY A LEAD AND NOT JUST AN EMAIL
Smartlead attributes an inbound reply through its LEAD record for the campaign. A message sent
from an unknown outside address into a connected mailbox may be seen by the mailbox and still not
produce an EMAIL_REPLY event with campaign attribution - which would give an ambiguous result on
the one test whose entire purpose is to be unambiguous. Adding the address as a real lead to an
ACTIVE campaign makes the reply a genuine, fully-attributed campaign reply.

TARGET
Campaign 3686187 - "[Events Visiting] AI4 2026 - Rune - Valids" - the only ACTIVE campaign, so its
sequence will actually fire. Inbox: whatever Smartlead assigns for that campaign; the send confirms
which one, and Nik replies to exactly that address.

WHAT THIS DOES
  DRY_RUN=1 (default): resolves the campaign, confirms it is ACTIVE, confirms the address is not
  already a lead anywhere, and prints the exact payload. No writes.
  DRY_RUN=0: adds the single lead.

It does NOT trigger a send - Smartlead's own scheduler does that on the campaign's schedule. The
script reports the campaign's schedule so Nik knows the window to watch.

Usage:  NIK_EMAIL=pii-c39bc547@example.invalid DRY_RUN=1 python r4_controlled_lead.py
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
DRY = os.environ.get("DRY_RUN", "1") != "0"
EMAIL = (os.environ.get("NIK_EMAIL") or "").strip().lower()
CID = int(os.environ.get("CAMPAIGN_ID", "3686187"))
UA = "Mozilla/5.0 janea-r4/1.0"

if not EMAIL or "@" not in EMAIL:
    print("NIK_EMAIL is required - the external address Nik will reply FROM.\n"
          "It must be an inbox he controls and that is NOT a janeasystems / janea* sending "
          "domain, or the reply will look like our own traffic.")
    sys.exit(2)


def sl(path, params=None, method="GET", body=None):
    q = dict(params or {}); q["api_key"] = SLK
    data = json.dumps(body).encode() if body is not None else None
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    try:
        r = urllib.request.Request(url, method=method, data=data,
                                   headers={"User-Agent": UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:400]}


camp = sl(f"/campaigns/{CID}")
print(f"campaign {CID}: {camp.get('name')!r}  status={camp.get('status')}")
if str(camp.get("status", "")).upper() != "ACTIVE":
    print(f"REFUSING: campaign is {camp.get('status')}, not ACTIVE - a non-active campaign will "
          "never send, so the lead would sit there and the gate would silently never open.")
    sys.exit(2)

if any(d in EMAIL.split("@")[-1] for d in ("janeasystems", "janeatech", "janeasoftware", "janea")):
    print(f"REFUSING: {EMAIL} looks like one of our own sending domains. The whole point is an "
          "EXTERNAL inbox - a reply from our own infrastructure proves nothing about inbound "
          "delivery.")
    sys.exit(2)

existing = sl("/leads", {"email": EMAIL})
if existing and existing.get("id"):
    print(f"\nalready a Smartlead lead: id={existing.get('id')}")
    for c in (existing.get("lead_campaign_data") or []):
        print(f"   in campaign {c.get('campaign_id')} {c.get('campaign_name')!r} "
              f"last_sent={c.get('last_sent_at')}")
    print("REFUSING to add again - reusing an existing lead makes the trace ambiguous.")
    sys.exit(2)
print(f"\n{EMAIL}: not currently a Smartlead lead anywhere - clean slate")

sched = {k: camp.get(k) for k in ("min_time_btwn_emails", "max_leads_per_day", "scheduler_cron_value",
                                  "start_date", "end_date", "send_as_plain_text", "track_settings")
         if k in camp}
print("\ncampaign schedule (this is the window Nik should watch for the send):")
print(json.dumps(sched, indent=2, ensure_ascii=False, default=str))

body = {"lead_list": [{"first_name": "Flip", "last_name": "Gate", "email": EMAIL,
                       "company_name": "Person-6d3f690f Test",
                       "custom_fields": {"Title": "WF-2R flip-gate probe"}}],
        "settings": {"ignore_global_block_list": True,
                     "ignore_unsubscribe_list": True,
                     "ignore_duplicate_leads_in_other_campaign": False}}
print(f"\n{'DRY-RUN - would POST' if DRY else 'POSTING'} /campaigns/{CID}/leads")
print(json.dumps(body, indent=2, ensure_ascii=False))

if not DRY:
    res = sl(f"/campaigns/{CID}/leads", None, "POST", body)
    print("\nresult:", json.dumps(res, ensure_ascii=False, default=str)[:600])
    if res.get("__err"):
        sys.exit(1)
    back = sl("/leads", {"email": EMAIL})
    ok = bool(back and back.get("id"))
    print(f"\nverified by re-read: {'lead ' + str(back.get('id')) if ok else 'NOT FOUND - the '
          'POST did not take'}")
    if ok:
        print(f"added {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}Z. "
              "Tell Nik to watch that inbox for the first send, then reply to the exact address "
              "it arrives FROM (not to any older thread).")
    sys.exit(0 if ok else 1)
