"""Build a lead_id -> person_id (+title, add_time, update_time) map for the whole account, once,
so the duplicate-forensics diagnosis can resolve any lead UUID instantly instead of re-scanning
57k+ leads per lookup. Read-only.
"""
import json
import os
import urllib.error
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-forensics/1.0"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "wf1-release-evidence", "lead_person_map.json")


def pd(path, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path,
                                       headers={"x-api-token": PDT, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=150) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            import time
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            raise
    return {}


leads, start = {}, 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    for L in b:
        leads[L["id"]] = {"person_id": L.get("person_id"), "title": L.get("title"),
                          "add_time": L.get("add_time"), "update_time": L.get("update_time"),
                          "owner_id": L.get("owner_id"), "creator_id": L.get("creator_id"),
                          "label_ids": L.get("label_ids")}
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    print(f"  scanned {start} leads...")
    if not b or not more.get("more_items_in_collection"):
        break

json.dump(leads, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print(f"\nwrote {OUT} ({len(leads)} leads)")
