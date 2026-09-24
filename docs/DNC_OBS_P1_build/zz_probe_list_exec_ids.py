import json, os, ssl, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
r = urllib.request.Request(BASE + "/api/v1/executions?workflowId=9aP2dP0jgAPFGDvA&limit=3",
                            headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
    d = json.load(x)
for e in d.get("data", []):
    print(e.get("id"), e.get("status"))
