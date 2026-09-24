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
WID = "Gncvjn1GKDTX13xA"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


execs = n8n(f"/api/v1/executions?workflowId={WID}&limit=1")
for ex in execs.get("data", []):
    eid = ex.get("id")
    print("execution", eid, ex.get("status"))
    full = n8n(f"/api/v1/executions/{eid}?includeData=true")
    err = (full.get("data", {}).get("resultData") or {}).get("error")
    print("top-level error:", json.dumps(err, indent=2)[:1500] if err else "(none)")
    run_data = ((full.get("data", {}).get("resultData") or {}).get("runData") or {})
    print("nodes that ran:", list(run_data.keys()))
    for nname, runs in run_data.items():
        for run in runs:
            if run.get("error"):
                print(f"--- {nname} error ---")
                print(json.dumps(run["error"], indent=2)[:1200])

n8n(f"/api/v1/workflows/{WID}/deactivate", "POST", {})
n8n(f"/api/v1/workflows/{WID}", "DELETE")
print("cleaned up", WID)
