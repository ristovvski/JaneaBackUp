#!/usr/bin/env python3
"""Bounce WF-2S once to clear orphan execution 14183 (running since 2026-08-07, ~4.2 days).

Deliberately AFTER the drain: 32 events > one orphan, and bouncing mid-replay would have risked the
recovery. Drain is confirmed complete (__sent_seen_v2 back above its pre-release size).

Cheapest possible action: deactivate, verify off, reactivate, verify on, confirm the orphan is gone
and the schedule resumes. staticData is NOT touched - a bounce must not disturb the stores we spent
the evening repairing, so their sizes are compared before and after.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2S = "6Y92ryBwYoy6z0Jx"
ORPHAN = "14183"


def n8n(p, q=None, method="GET", body=None, attempt=0):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(p, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {p} FAILED: HTTP {e.code}")


def running():
    p = n8n("/api/v1/executions", {"workflowId": WF2S, "limit": 50, "status": "running"})
    return [e["id"] for e in ((p or {}).get("data") or [])]


def stores(w):
    sd = (w.get("staticData") or {}).get("global") or {}
    return {k: (len(v) if isinstance(v, dict) else v) for k, v in sd.items()
            if isinstance(v, (dict, str, int))}


before = n8n(f"/api/v1/workflows/{WF2S}")
b_stores = stores(before)
print(f"before: active={before.get('active')} versionId={before.get('versionId')}")
print(f"        running executions: {running()}")
print(f"        staticData: {json.dumps(b_stores)}")

print("\ndeactivating...")
n8n(f"/api/v1/workflows/{WF2S}/deactivate", None, "POST", {})
time.sleep(8)
mid = n8n(f"/api/v1/workflows/{WF2S}")
print(f"        active={mid.get('active')}  running={running()}")

print("reactivating...")
for attempt in range(6):
    n8n(f"/api/v1/workflows/{WF2S}/activate", None, "POST", {})
    time.sleep(5)
    if n8n(f"/api/v1/workflows/{WF2S}").get("active"):
        break
    print(f"   retry {attempt + 1}")

after = n8n(f"/api/v1/workflows/{WF2S}")
a_stores = stores(after)
still = running()
print(f"\nafter : active={after.get('active')} versionId={after.get('versionId')}")
print(f"        running executions: {still}")
print(f"        staticData: {json.dumps(a_stores)}")

problems = []
if not after.get("active"):
    problems.append("WF-2S DID NOT REACTIVATE")
if ORPHAN in still:
    problems.append(f"orphan {ORPHAN} still running")
for k, v in b_stores.items():
    if isinstance(v, int) and a_stores.get(k) != v:
        problems.append(f"staticData.{k} changed {v} -> {a_stores.get(k)}")
print(f"\nverdict: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
if not problems:
    print(f"  orphan {ORPHAN} cleared; schedule resumes on the next 15-min tick")
sys.exit(1 if problems else 0)
