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
ids = [25112064, 13015123, 16340280, 25035678, 25151686, 16029123, 21659, 9165]
users = {u["id"]: u.get("name") for u in (pd("/users", {}).get("data") or [])}
for i in ids:
    print(i, "->", users.get(i, "NOT A USER (org/other id)"))
