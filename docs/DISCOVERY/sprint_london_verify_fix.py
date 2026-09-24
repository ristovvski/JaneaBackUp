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

missing = json.load(open("sprint_london_missing.json", encoding="utf-8"))["missing"]
sample = missing[:10]
for r in sample:
    email = r["email"]
    s = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true", "limit": 1})
    items = ((s or {}).get("data") or {}).get("items") or []
    print(f"  {email}: found={len(items)>0}  {'person_id='+str(items[0]['item']['id']) if items else ''}")
