#!/usr/bin/env python3
"""State before repairing Person-9979a87c (person 85517): does he have a lead to label at all, and
which campaign does this InMail belong to? Normalize showed `campaign: {}` - empty - so the campaign
cannot be assumed; read it from the event and from any existing lead."""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


leads = (pd("/v1/leads?limit=50&person_id=85517") or {}).get("data") or []
print(f"person 85517 leads: {len(leads)}")
for l in leads:
    print(f"   id={l.get('id')}")
    print(f"     title={l.get('title')!r}")
    print(f"     labels={l.get('label_ids')}")
    print(f"     campaign_field={l.get('1cd81dfcac8a5583935ff4b60e284d0e580db0b6')!r}")
    print(f"     owner={l.get('owner_id')} archived={l.get('is_archived')}")
    acts = (pd(f"/api/v2/activities?lead_id={l.get('id')}&limit=10") or {}).get("data") or []
    print(f"     activities={len(acts)}")
    for a in acts:
        print(f"        {a.get('id')} {str(a.get('subject'))[:50]!r} {a.get('due_date')}")

d = n8n("/api/v1/executions/16703?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
print("\n--- campaign / routing info on the event ---")
print(f"  campaign: {json.dumps(nz.get('campaign'), ensure_ascii=False)}")
print(f"  event_trio: {json.dumps(nz.get('event_trio'), ensure_ascii=False)[:300]}")
print(f"  is_inmail={nz.get('is_inmail')} conv={str(nz.get('conv'))[:30]}")
print(f"  sender: {json.dumps(nz.get('sender'), ensure_ascii=False)[:180]}")
raw = rd["Webhook"][0]["data"]["main"][0][0]["json"]
raw = raw.get("body", raw)
print(f"\n  raw webhook top-level keys: {sorted(raw.keys())}")
for k in ("campaign", "campaignId", "campaign_id", "campaign_name", "campaignName", "list"):
    if k in raw:
        print(f"    {k} = {json.dumps(raw[k], ensure_ascii=False)[:200]}")
print(f"\n  messages: {json.dumps(nz.get('msgs'), ensure_ascii=False)[:400]}")
