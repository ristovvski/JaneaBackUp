import os, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json"}
r = requests.get(B + "/auth/CheckApiKey", headers=h, timeout=30)
print("CheckApiKey:", r.status_code, r.text[:300])
r2 = requests.post(B + "/campaign/GetAll", headers=h, json={"offset": 0, "limit": 5}, timeout=30)
print("GetAll campaigns:", r2.status_code)
if r2.ok:
    data = r2.json()
    items = data.get("items") if isinstance(data, dict) else data
    print("type:", type(data).__name__, "count:", len(items) if items else 0)
    if items:
        print("sample:", [{"id": c.get("id"), "name": c.get("name")} for c in items[:5]])
else:
    print(r2.text[:300])
