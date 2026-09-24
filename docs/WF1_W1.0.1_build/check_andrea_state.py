#!/usr/bin/env python3
"""A read timed out mid-run. Before ANY retry: did the lead get created, labelled, or an activity
written? Re-running blind is how you get a duplicate lead. Read the CRM, then decide."""
import json, os, ssl, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


leads = (pd("/v1/leads?limit=50&person_id=69696") or {}).get("data") or []
print(f"person 69696 leads: {len(leads)}")
for l in leads:
    print(f"   id={l.get('id')}")
    print(f"   title={l.get('title')!r}")
    print(f"   labels={l.get('label_ids')}")
    print(f"   created={l.get('add_time')}  owner={l.get('owner_id')}")
    acts = (pd(f"/api/v2/activities?lead_id={l.get('id')}&limit=10") or {}).get("data") or []
    print(f"   activities: {len(acts)}")
    for ac in acts:
        print(f"      {ac.get('id')} {str(ac.get('subject'))[:52]!r} "
              f"done={ac.get('done')} note_len={len(str(ac.get('note') or ''))}")
if not leads:
    print("   -> nothing was written. Safe to re-run the repair.")
