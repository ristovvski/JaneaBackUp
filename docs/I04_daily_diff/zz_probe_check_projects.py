import json, os, ssl, urllib.request, urllib.error

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


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=ctx) as x:
        return json.load(x)


print("--- projects ---")
try:
    print(json.dumps(n8n("/api/v1/projects"), indent=2)[:3000])
except urllib.error.HTTPError as e:
    print("failed:", e.code, e.read()[:500])

print("--- one of my deployed workflows (weekly reconciliation) ---")
w = n8n("/api/v1/workflows/gjVZkkvm05jj8CNM")
print(json.dumps({k: v for k, v in w.items() if k in ("id", "name", "homeProject", "sharedWithProjects")}, indent=2, default=str))
