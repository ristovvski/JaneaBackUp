import os, json, ssl
import urllib.request, urllib.parse
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    r = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x)
wf = n8n(f"/api/v1/workflows/{WF2}")
for n in wf.get("nodes", []):
    if n["name"] in ("Classify Body", "LLM Classify", "Classify Parse", "IF Classify Enabled"):
        print("===", n["name"], "| type:", n["type"], "===")
        p = n["parameters"]
        if n["type"] == "n8n-nodes-base.httpRequest":
            print(json.dumps(p, indent=2, default=str)[:3000])
        else:
            print(p.get("jsCode", json.dumps(p))[:3000])
        print()
