#!/usr/bin/env python3
"""B4 pass 2 - create the Pipedrive person + lead for the flip-gate address, so the CRM half of
the smoke becomes measurable.

WHY IT IS MISSING: WF-2's reply branch RESOLVES an existing lead; it does not create one. Leads are
created on SENT. The flip-gate address was sent to on 2026-08-06 while WF-2 was still in shadow, so
no person was ever created and the reply had nothing to attach to (lead_id: None, no label patch,
no activity). That is correct behaviour, not a defect - the fixture was simply incomplete.

Built to WF-2's own lead convention so the smoke exercises the real path:
  title  {campaign_id} - {campaign_name} - {name}
  owner  Melisa (16340280) · labels [1. Cold] · channel 578
  fields lead_campaign = campaign name, lead_opportunity_type = 480

NAMED 'TEST' deliberately - it must be obvious to anyone in Pipedrive that this is not a prospect
and must never be distributed to a salesperson.
"""
import json, os, ssl, sys, urllib.error, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
DRY = os.environ.get("DRY_RUN", "1") != "0"
HERE = os.path.dirname(os.path.abspath(__file__))

EMAIL = "pii-c61c7d08@example.invalid"
NAME = "ZZ FLIP-GATE TEST (do not distribute)"
CID = 3686187
CAMPAIGN = "[Events Visiting] AI4 2026 - Rune - Valids"
OWNER = 16340280
COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
F_LEAD_CAMPAIGN = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP_TYPE = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
OPP_VALUE = 480
CHANNEL = 578


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea-b4b/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:400]}


srch = pd(f"/v1/persons/search?term={EMAIL}&fields=email&exact_match=true")
items = ((srch or {}).get("data") or {}).get("items") or []
person_id = items[0]["item"]["id"] if items else None
print(f"existing person for {EMAIL}: {person_id}")

person_body = {"name": NAME, "owner_id": OWNER,
               "emails": [{"value": EMAIL, "primary": True, "label": "work"}]}
print(f"\n{'DRY-RUN' if DRY else 'LIVE'}")
if not person_id:
    print(f"  [A] POST /api/v2/persons  {json.dumps(person_body, ensure_ascii=False)}")
else:
    print("  [A] person exists - skipping creation")

if not DRY and not person_id:
    r = pd("/api/v2/persons", "POST", person_body)
    person_id = ((r or {}).get("data") or {}).get("id")
    print(f"      -> person {person_id}" if person_id else f"      -> FAILED {json.dumps(r)[:300]}")
    if not person_id:
        sys.exit(1)

lead_body = {"title": f"{CID} - {CAMPAIGN} - {NAME}", "person_id": person_id,
             "owner_id": OWNER, "label_ids": [COLD],
             F_LEAD_CAMPAIGN: CAMPAIGN, F_OPP_TYPE: OPP_VALUE, "channel": CHANNEL}
existing_leads = []
if person_id:
    existing_leads = (pd(f"/v1/leads?limit=50&person_id={person_id}&archived_status=all")
                      or {}).get("data") or []
print(f"  existing leads for this person: {len(existing_leads)}")
for L in existing_leads:
    print(f"     {L.get('id')}  {L.get('title')}")

if existing_leads:
    print("  [B] lead already exists - skipping creation")
    lead_id = existing_leads[0]["id"]
else:
    print(f"  [B] POST /v1/leads  title={lead_body['title']!r}")
    lead_id = None
    if not DRY:
        r = pd("/v1/leads", "POST", lead_body)
        lead_id = ((r or {}).get("data") or {}).get("id")
        print(f"      -> lead {lead_id}" if lead_id else f"      -> FAILED {json.dumps(r)[:300]}")

if DRY:
    print("\n--deploy not given (DRY_RUN=1): nothing written.")
    sys.exit(0)

back = (pd(f"/v1/leads/{lead_id}") or {}).get("data") or {} if lead_id else {}
ok = bool(lead_id) and back.get("person_id") == person_id
print(f"\nverified by re-read: lead={lead_id} person={back.get('person_id')} "
      f"labels={back.get('label_ids')} owner={back.get('owner_id')}")
print(f"campaign field: {back.get(F_LEAD_CAMPAIGN)!r}")
print(f"\nfixture: {'READY' if ok else 'INCOMPLETE'}")
json.dump({"email": EMAIL, "person_id": person_id, "lead_id": lead_id, "campaign_id": CID},
          open(os.path.join(HERE, "wf1-release-evidence", "b4b_test_fixture.json"), "w",
               encoding="utf-8"), indent=2, default=str)
sys.exit(0 if ok else 1)
