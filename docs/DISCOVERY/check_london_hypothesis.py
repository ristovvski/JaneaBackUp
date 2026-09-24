import os, json, ssl
import urllib.request, urllib.parse
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
    with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
        return json.load(x)

persons = json.load(open("sprint_persons_fields.json", encoding="utf-8"))
london = [v for v in persons.values() if v.get("campaign") and "london" in str(v.get("campaign")).lower()
          and "sales sprint" in str(v.get("campaign")).lower()][:8]
for v in london:
    p = (pd(f"/persons/{v['id']}") or {}).get("data") or {}
    print(v["id"], "campaign=", v.get("campaign")[:40], "| hypothesis=", repr(p.get(F_HYPO)), "| event_name=", repr(p.get(F_EVENT)))
