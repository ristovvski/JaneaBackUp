import os, json, ssl
import urllib.request, urllib.parse
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)
page = pd("/persons", {"start": 0, "limit": 3, "sort": "add_time DESC"})
for p in page.get("data") or []:
    print(json.dumps({"id": p.get("id"), "email": p.get("email"), "owner_id": p.get("owner_id"),
        "add_time": p.get("add_time"), "event_field": p.get("ab5540d2ca45905dfb1434c0fe4971cc5790de3f"),
        "hypo_field": p.get("8bdae1a91272e92b335e9e99f668cde659b6daae")}, default=str)[:500])
print("\nadditional_data.pagination:", page.get("additional_data"))
# also check /leads shape for person_id + the campaign field
page2 = pd("/leads", {"start": 0, "limit": 2, "sort": "add_time DESC", "archived_status": "all"})
for l in page2.get("data") or []:
    print("\nLEAD:", json.dumps({"id": l.get("id"), "title": l.get("title"), "person_id": l.get("person_id"),
        "campfield": l.get("1cd81dfcac8a5583935ff4b60e284d0e580db0b6")}, default=str))
