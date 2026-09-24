#!/usr/bin/env python3
"""#27 item 2 — the three ALIAS replies from 2026-07-31 that the old Normalize misattributed.

  pii-6e4e8b43@example.invalid   replied from kevin.conrad.morales@   person 83499
  pii-1011b46b@example.invalid          replied from jfarrar@                person 83604
  pii-399e6070@example.invalid       replied from ravery@                 person 83661

All three are the SAME human under a second address - the originally-specified rule
(sender != lead -> suppress) would have silenced every one. They need '3. Responded' + a reply
activity, on the lead of the CAMPAIGN lead, not of the alias.

State first: which already have leads, which labels, which already carry an activity - so the
repair is idempotent and cannot double-write. Read only.
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"

WHO = [("Person-65862a8f", 83499, "pii-6e4e8b43@example.invalid",
        "pii-9efda044@example.invalid"),
       ("Person-9c782f71", 83604, "pii-1011b46b@example.invalid", "pii-e56d5459@example.invalid"),
       ("Person-1a93b995", 83661, "pii-399e6070@example.invalid", "pii-3d090878@example.invalid")]


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


for name, pid, lead_email, alias in WHO:
    print(f"=== {name}  person {pid} ===")
    p = (pd(f"/api/v2/persons/{pid}") or {}).get("data") or {}
    emails = [e.get("value") for e in (p.get("emails") or [])]
    print(f"  person name={p.get('name')!r} emails={emails}")
    print(f"  campaign lead address {lead_email!r} on person: {lead_email in emails}")
    print(f"  alias address         {alias!r} on person: {alias in emails}")

    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
    print(f"  leads: {len(leads)}")
    for l in leads:
        lid = l.get("id")
        labels = l.get("label_ids") or []
        acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=20") or {}).get("data") or []
        replies = [a for a in acts if "reply" in str(a.get("subject") or "").lower()]
        print(f"    {lid}")
        print(f"      title={str(l.get('title'))[:60]!r}")
        print(f"      labels={len(labels)} responded={'YES' if L_RESPONDED in labels else 'no'}")
        print(f"      campaign_field={l.get('1cd81dfcac8a5583935ff4b60e284d0e580db0b6')!r}")
        print(f"      activities={len(acts)} reply-activities={len(replies)}")
        for a in replies:
            print(f"         {a.get('id')} {str(a.get('subject'))[:46]!r} {a.get('due_date')}")
    print()
