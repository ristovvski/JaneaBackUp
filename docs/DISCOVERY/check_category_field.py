import os, json, requests
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    r = requests.get(f"https://janeasystems.pipedrive.com/api/v1{path}", params=q, timeout=45)
    return r.json()
for ep in ("/personFields", "/leadFields"):
    fields = pd(ep, {"start": 0, "limit": 500}).get("data") or []
    matches = [f for f in fields if any(t in (f.get("name") or "").lower() for t in ("categor", "sentiment", "reply"))]
    print(ep, "matches:", [(f["key"], f["name"], f["field_type"]) for f in matches])
