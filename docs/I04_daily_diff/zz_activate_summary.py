import json, os, ssl, time, urllib.request
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
WID = "8sT1XjDDVmrz05CA"

req = urllib.request.Request(BASE + f"/api/v1/workflows/{WID}/activate", method="POST", data=b"{}",
                              headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30, context=ctx) as x:
    pass
time.sleep(2)
req2 = urllib.request.Request(BASE + f"/api/v1/workflows/{WID}", headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
with urllib.request.urlopen(req2, timeout=30, context=ctx) as x:
    print("active:", json.load(x).get("active"))
