#!/usr/bin/env python3
"""Gate v2 staged validation: (1) one batch call of 200 synthetic rows -- confirm one execution,
correct counts, log duration/memory; (2) per-row burst at 10, then 50, then 200 concurrent
single-row calls -- confirm all queue+drain, zero crashes, gate stays active throughout."""
import concurrent.futures
import json, os, ssl, sys, time, urllib.error, urllib.request

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
WID = "9aP2dP0jgAPFGDvA"
WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def fire(rows, timeout=60):
    payload = {"rows": rows}
    req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = json.loads(r.read())
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body, time.time() - t0


def check_active():
    full = n8n(f"/api/v1/workflows/{WID}")
    return full.get("active")


print("=== TEST 1: batch of 200 synthetic rows, one call ===")
rows_200 = [{"label": f"batch-{i}", "email": f"batch-probe-{i}@example.invalid"} for i in range(200)]
status, body, elapsed = fire(rows_200, timeout=90)
print(f"HTTP {status}  wall_time={elapsed:.2f}s")
print("counts:", body.get("counts"))
print("self-reported duration_ms:", body.get("duration_ms") if "duration_ms" in body else "(check a 'rows' entry)")
if body.get("rows"):
    print("sample row keys:", list(body["rows"][0].keys()))
print("gate active:", check_active())

print("\n=== TEST 2a: per-row burst, 10 concurrent ===")
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    futs = [ex.submit(fire, [{"label": f"burst10-{i}", "email": f"burst10-probe-{i}@example.invalid"}]) for i in range(10)]
    results = [f.result() for f in futs]
statuses = {}
for s, _, _ in results:
    statuses[s] = statuses.get(s, 0) + 1
print("status distribution:", statuses)
print("gate active:", check_active())

print("\n=== TEST 2b: per-row burst, 50 concurrent ===")
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    futs = [ex.submit(fire, [{"label": f"burst50-{i}", "email": f"burst50-probe-{i}@example.invalid"}]) for i in range(50)]
    results = [f.result() for f in futs]
statuses = {}
for s, _, _ in results:
    statuses[s] = statuses.get(s, 0) + 1
print("status distribution:", statuses)
print("gate active:", check_active())

print("\n=== TEST 2c: per-row burst, 200 concurrent ===")
with concurrent.futures.ThreadPoolExecutor(max_workers=200) as ex:
    futs = [ex.submit(fire, [{"label": f"burst200-{i}", "email": f"burst200-probe-{i}@example.invalid"}], 120) for i in range(200)]
    results = [f.result() for f in futs]
statuses = {}
for s, _, _ in results:
    statuses[s] = statuses.get(s, 0) + 1
print("status distribution:", statuses)
elapsed_all = [e for _, _, e in results]
print(f"per-request wall time: min={min(elapsed_all):.2f}s max={max(elapsed_all):.2f}s avg={sum(elapsed_all)/len(elapsed_all):.2f}s")
print("gate active:", check_active())

print("\n=== TEST 3: Barry fixture in per-row mode ===")
s1, b1, _ = fire([{"label": "known-blocked", "email": "pii-d50f3785@example.invalid"}])
s2, b2, _ = fire([{"label": "known-clean", "email": "final-clean-probe@example.invalid"}])
print("blocked call:", s1, b1.get("counts"))
print("clean call:", s2, b2.get("counts"))
print("gate active:", check_active())
