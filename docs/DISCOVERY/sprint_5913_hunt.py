"""READ-ONLY background scan: pull ALL Pipedrive persons with the fields needed to hunt Melisa's
5913-count filter: Source, Medium, lh_campaign_name (person-level Campaign field), email, add_time.
Slow (56k+ persons, ~114 pages) - run in background."""
import json, os, ssl, sys
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))

F_SOURCE = "6070ae31f09228f95048b0f68982b1cd4d3a684a"
F_MEDIUM = "961698945b0329b367da11916a94f10ff7ba71fe"
F_CAMPAIGN = "86157bb49563191c17b4dc62580525f84417524c"
F_LIURL = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"


def pd(path, params=None, tries=4):
    import time
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


persons = {}
start = 0
pages = 0
while True:
    page = pd("/persons", {"start": start, "limit": 500, "sort": "add_time DESC"})
    if "__err" in page:
        print("ERROR:", page); break
    rows = page.get("data") or []
    if not rows:
        break
    for p in rows:
        em = p.get("email")
        email = em[0].get("value") if isinstance(em, list) and em else None
        persons[p["id"]] = {
            "id": p["id"], "email": email, "add_time": p.get("add_time"),
            "source": p.get(F_SOURCE), "medium": p.get(F_MEDIUM),
            "campaign": p.get(F_CAMPAIGN), "li_url": p.get(F_LIURL), "event_name": p.get(F_EVENT),
        }
    pages += 1
    ad = (page.get("additional_data") or {}).get("pagination") or {}
    if not ad.get("more_items_in_collection"):
        break
    start = ad.get("next_start") or (start + len(rows))
    if pages % 20 == 0:
        print(f"...{pages} pages, {len(persons)} persons")

print(f"TOTAL persons scanned: {pages} pages, {len(persons)} persons")
with open(os.path.join(HERE, "sprint_persons_fields.json"), "w", encoding="utf-8") as f:
    json.dump(persons, f, default=str)
print("wrote sprint_persons_fields.json")
