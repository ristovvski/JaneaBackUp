import os, json, requests
SLK = os.environ["SMARTLEAD_API_KEY"]
def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    r = requests.get(f"https://server.smartlead.ai/api/v1{path}", params=q, timeout=45)
    return r.json()
page = sl("/campaigns/3565651/leads", {"offset": 0, "limit": 3})
print("top-level type:", type(page).__name__, "keys:" if isinstance(page, dict) else "")
if isinstance(page, dict):
    print(list(page.keys()))
rows = page.get("data") if isinstance(page, dict) else page
print("rows type:", type(rows).__name__, "len:", len(rows) if hasattr(rows,'__len__') else "n/a")
if rows:
    print(json.dumps(rows[0], indent=2, default=str)[:2000])
