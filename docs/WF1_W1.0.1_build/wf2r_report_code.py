import os, json, ssl
import urllib.request, urllib.parse
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2R = "U8Bb7Pdq7S6nzYPa"
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    r = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x)
wf = n8n(f"/api/v1/workflows/{WF2R}")
for n in wf["nodes"]:
    if n["name"] in ("Summary", "WF-2R Report"):
        print("===", n["name"], "| type:", n["type"], "===")
        p = n["parameters"]
        print(p.get("jsCode", json.dumps(p, indent=2, default=str)[:2000]) if "jsCode" in p else json.dumps(p, indent=2, default=str)[:2500])
        print()
