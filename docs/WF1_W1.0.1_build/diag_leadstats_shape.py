import os, json, urllib.request, urllib.parse
SLK = os.environ["SMARTLEAD_API_KEY"]
UA = "Mozilla/5.0 janea-forensics/1.0"
url = "https://server.smartlead.ai/api/v1/campaigns/3686193/leads-statistics?" + urllib.parse.urlencode({"limit": 5, "offset": 0, "api_key": SLK})
r = urllib.request.Request(url, headers={"User-Agent": UA})
with urllib.request.urlopen(r, timeout=45) as x:
    data = json.load(x)
print("top-level type:", type(data).__name__, "keys:" if isinstance(data, dict) else "n/a", list(data.keys()) if isinstance(data, dict) else None)
rows = data.get("data") if isinstance(data, dict) else data
print("rows type:", type(rows).__name__, "len:", len(rows) if hasattr(rows,'__len__') else "n/a")
if rows:
    print(json.dumps(rows[0], indent=2, default=str)[:3000])
