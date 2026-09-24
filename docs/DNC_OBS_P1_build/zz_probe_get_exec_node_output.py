import json, os, ssl, sys, urllib.request
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
EID = sys.argv[1]
NODE = sys.argv[2]
r = urllib.request.Request(BASE + f"/api/v1/executions/{EID}?includeData=true",
                            headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
    d = json.load(x)
rd = (d.get("data", {}).get("resultData") or {})
run = (rd.get("runData") or {}).get(NODE)
print(json.dumps(run, indent=2)[:3000])
