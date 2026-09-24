"""I0 — who created yesterday's ~64 new leads? Read-only.

'Yesterday' relative to today (2026-08-05) = 2026-08-04. Sorted/paginated reads only (the banned
pagination-class rule). Cross-references creator_id against the Pipedrive users list and flags
anything matching a known automation actor (our WF-1/WF-2 API token's owner, Marci, Melisa) vs an
unexplained human/API creator.
"""
import json
import os
import urllib.error
import urllib.request
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-flipday/1.0"
DAY = "2026-08-04"


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


users = {u["id"]: f"{u.get('name')} <{u.get('email')}>"
         for u in (pd("/v1/users").get("data") or [])}

leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break

yday = [L for L in leads if str(L.get("add_time") or "").startswith(DAY)]
print(f"leads scanned: {len(leads)}")
print(f"leads created on {DAY}: {len(yday)}")

by_creator = Counter(L.get("creator_id") for L in yday)
print("\nby creator:")
for cid, n in by_creator.most_common():
    print(f"  {n:>3}  {users.get(cid, cid)}  (creator_id={cid})")

print("\nsample titles per creator:")
seen = set()
for L in sorted(yday, key=lambda x: str(x.get("add_time"))):
    cid = L.get("creator_id")
    if cid in seen:
        continue
    seen.add(cid)
    print(f"  [{users.get(cid, cid)}] {L.get('add_time')}  {str(L.get('title'))[:70]}")

# distinguish "our automation" (WF-1/WF-2 API token) from anything else
print("\ncampaign-field / channel breakdown (helps tell WF-1 LinkedIn vs WF-2 email vs manual):")
chan = Counter(L.get("channel") for L in yday)
for c, n in chan.most_common():
    print(f"  channel={c}: {n}")
