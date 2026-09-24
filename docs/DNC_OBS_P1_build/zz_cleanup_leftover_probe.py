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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


page = n8n("/api/v1/workflows?limit=250")
leftovers = [w for w in page.get("data", []) if w["name"].startswith("zz_probe") or w["name"].startswith("zz_")]
for w in leftovers:
    print(w["id"], w["name"], w.get("active"))
    try:
        if w.get("active"):
            n8n(f"/api/v1/workflows/{w['id']}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{w['id']}", "DELETE")
        print("  cleaned up")
    except Exception as e:
        print("  failed:", e)
