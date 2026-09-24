"""INVESTIGATION - burst of LinkedHelper Slack posts across OLD campaigns, 7 leads.

Step 1: ground truth per lead - the lead, its person, and whatever changelog Pipedrive will give up.
Tests a person-level flow/changelog endpoint rather than assuming it doesn't exist (the earlier
'creator_id != update-author' finding was specifically about LEADS; person-level history has not
been tested this session).
"""
import json
import os
import urllib.error
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-invest/1.0"
LEAD_PREFIXES = ["b2ecfa40-3e8a", "13bdaaa0-180b", "3fb836e0-1d81", "20473110-34ef",
                 "ecd18250-faea", "47f28490-0130", "ad38e480-faef"]


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=90) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


users = {u["id"]: f"{u.get('name')} <{u.get('email')}>"
         for u in (pd("/v1/users")[1].get("data") or [])}

print("=" * 100)
print("FINDING THE 7 LEADS")
print("=" * 100)
leads, start = [], 0
while True:
    st, d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
print(f"leads scanned: {len(leads)}")

found = {}
for pre in LEAD_PREFIXES:
    L = next((x for x in leads if str(x.get("id", "")).startswith(pre)), None)
    found[pre] = L
    if not L:
        print(f"\n[{pre}] NOT FOUND")
        continue
    print(f"\n[{pre}] lead={L['id']}")
    print(f"    title={L.get('title')}")
    print(f"    person_id={L.get('person_id')}  add_time={L.get('add_time')}  "
          f"update_time={L.get('update_time')}")
    print(f"    labels={L.get('label_ids')}  owner={users.get(L.get('owner_id'))}  "
          f"creator={users.get(L.get('creator_id'))}")

print("\n" + "=" * 100)
print("PERSON RECORDS + TESTING FOR A CHANGELOG/FLOW ENDPOINT")
print("=" * 100)
tested_flow_endpoint = False
for pre, L in found.items():
    if not L or not L.get("person_id"):
        continue
    pid = L["person_id"]
    st, p = pd(f"/api/v2/persons/{pid}")
    pdata = p.get("data") or {}
    print(f"\n[{pre}] person={pid}  name={pdata.get('name')}")
    print(f"    add_time={pdata.get('add_time')}  update_time={pdata.get('update_time')}")
    print(f"    owner_id={pdata.get('owner_id')} ({users.get(pdata.get('owner_id'))})")

    if not tested_flow_endpoint:
        tested_flow_endpoint = True
        print("\n  -- probing for a person-level changelog/flow endpoint (v1) --")
        for ep in (f"/v1/persons/{pid}/flow", f"/v1/persons/{pid}/changelog",
                  f"/v1/personFields/{pid}/flow"):
            st2, r2 = pd(ep)
            print(f"    {ep} -> {st2}  {str(r2)[:200] if st2 != 200 else 'OK: ' + str(r2)[:300]}")
