#!/usr/bin/env python3
"""Fire 12 CONCURRENT single-row requests at the live gate (mimicking Clay's per-row pattern, but
at a small, safe scale -- 12 concurrent, not hundreds) to verify the concurrency guard actually
kicks in past GATE_MAX_CONCURRENT=5: expect a mix of 200s and 429s, never a crash, and the
workflow must stay active afterward. This exercises the real fail-open path too, since
dnc_gate_concurrency doesn't exist yet -- if the guard were NOT fail-open, this would throw
instead of just letting everything through as 200 (a real, useful signal either way)."""
import concurrent.futures
import json, os, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WID = "9aP2dP0jgAPFGDvA"
WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"


def fire(i):
    payload = {"rows": [{"label": f"burst-{i}", "email": f"burst-probe-{i}@example.invalid"}]}
    req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            body = json.loads(r.read())
            return i, r.status, body.get("error") or body.get("counts")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return i, e.code, body.get("error") or body


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
    results = list(ex.map(fire, range(12)))

for i, status, info in sorted(results):
    print(f"req {i}: HTTP {status}  {info}")

status_counts = {}
for _, s, _ in results:
    status_counts[s] = status_counts.get(s, 0) + 1
print("\nstatus distribution:", status_counts)

time.sleep(2)
full = n8n(f"/api/v1/workflows/{WID}")
print("gate active after burst:", full.get("active"))
