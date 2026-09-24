"""C2 prep - baseline activity state on the two leads whose backfill write adds 'responded'
(Rishab a81299b0, Andrew 8d9a2ab0), so the Handover guard can tell 'pre-existing' from 'newly minted
by Pipedrive's native automation' after the write. Read-only.
"""
import json
import os
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-flipday/1.0"
LEADS = {"Person-ef1ea617": "a81299b0", "Andrew Miller-McKeever": "8d9a2ab0"}


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.load(x)


leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break

for name, prefix in LEADS.items():
    L = next((x for x in leads if str(x.get("id", "")).startswith(prefix)), None)
    if not L:
        print(f"{name}: lead not found with prefix {prefix}")
        continue
    print(f"\n{name}  lead={L['id']}  person={L.get('person_id')}  labels={L.get('label_ids')}")
    acts = pd(f"/v1/activities?lead_id={L['id']}&done=0&limit=100")
    open_acts = acts.get("data") or []
    print(f"  OPEN activities right now: {len(open_acts)}")
    for a in open_acts or []:
        print(f"    id={a['id']} type={a.get('type')} subject={a.get('subject')!r} "
              f"owner={a.get('owner_id')} add_time={a.get('add_time')}")
    all_acts = pd(f"/v1/activities?lead_id={L['id']}&limit=100")
    print(f"  ALL activities (incl done): {len(all_acts.get('data') or [])}")
    for a in (all_acts.get("data") or [])[:6]:
        print(f"    id={a['id']} type={a.get('type')} subject={str(a.get('subject'))[:40]!r} "
              f"done={a.get('done')} owner={a.get('owner_id')}")
