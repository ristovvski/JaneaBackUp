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
config_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
print("parameters top-level keys:", list(config_node["parameters"].keys()))
print(json.dumps(config_node["parameters"], indent=2, default=str)[:1500])
