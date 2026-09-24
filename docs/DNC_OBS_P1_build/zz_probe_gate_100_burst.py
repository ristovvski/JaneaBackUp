#!/usr/bin/env python3
"""Narrow the ceiling: 100 concurrent single-row calls (between the confirmed-safe 50 and the
confirmed-too-much 200)."""
import concurrent.futures
import json, os, ssl, time, urllib.error, urllib.request

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
WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"


def fire(rows, timeout=90):
    payload = {"rows": rows}
    req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = json.loads(r.read())
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, {}, time.time() - t0
    except Exception as e:
        return -1, {"exc": str(e)}, time.time() - t0


print("=== 100 concurrent single-row calls ===")
with concurrent.futures.ThreadPoolExecutor(max_workers=100) as ex:
    futs = [ex.submit(fire, [{"label": f"burst100-{i}", "email": f"burst100-probe-{i}@example.invalid"}]) for i in range(100)]
    results = [f.result() for f in futs]
statuses = {}
for s, _, _ in results:
    statuses[s] = statuses.get(s, 0) + 1
print("status distribution:", statuses)
elapsed_all = [e for _, _, e in results]
print(f"per-request wall time: min={min(elapsed_all):.2f}s max={max(elapsed_all):.2f}s avg={sum(elapsed_all)/len(elapsed_all):.2f}s")
