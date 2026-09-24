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
for pid in [59555, 33126, 61354]:
    cl = (pd(f"/persons/{pid}/changelog", {"start": 0, "limit": 15}) or {}).get("data") or []
    print(f"--- person {pid} recent changelog ---")
    for row in cl[:6]:
        print("  ", row.get("time"), row.get("field_key"), "->", str(row.get("new_value"))[:40],
              "| actor", row.get("actor_user_id"), row.get("change_source"), row.get("change_source_user_agent"))
