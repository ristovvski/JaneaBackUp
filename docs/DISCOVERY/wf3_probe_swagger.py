import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
h = {"X-API-KEY": K, "accept": "application/json"}
for url in [
    "https://api.heyreach.io/api/public/swagger/index.html",
    "https://api.heyreach.io/api/public/swagger/v1/swagger.json",
    "https://api.heyreach.io/swagger/v1/swagger.json",
    "https://api.heyreach.io/api/public/swagger.json",
]:
    try:
        r = requests.get(url, headers=h, timeout=20)
        print(url, "->", r.status_code, "len=", len(r.text))
        if r.status_code == 200 and "swagger" in url.lower() and r.text.strip().startswith("{"):
            d = r.json()
            paths = [p for p in d.get("paths", {}).keys() if "conversat" in p.lower() or "inbox" in p.lower() or "message" in p.lower()]
            print("  relevant paths:", paths)
    except Exception as e:
        print(url, "ERR", str(e)[:150])
