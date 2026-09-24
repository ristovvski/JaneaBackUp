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
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
for pid, label in [(83546, "pii-6f8f48e5@example.invalid (Make-labeled Responded)"),
                   (83648, "pii-567b1851@example.invalid (Make-labeled Responded)")]:
    p = (pd(f"/persons/{pid}") or {}).get("data") or {}
    print(label, "-> event_name:", repr(p.get(F_EVENT)), "| hypothesis:", repr(p.get(F_HYPO)),
          "| add_time:", p.get("add_time"))
    cl = (pd(f"/persons/{pid}/changelog", {"start": 0, "limit": 30}) or {}).get("data") or []
    for row in cl:
        if row.get("field_key") in (F_EVENT, F_HYPO):
            print("   field write:", row.get("time"), row.get("field_key"), "->", row.get("new_value"),
                  "actor", row.get("actor_user_id"), row.get("change_source"), row.get("change_source_user_agent"))
