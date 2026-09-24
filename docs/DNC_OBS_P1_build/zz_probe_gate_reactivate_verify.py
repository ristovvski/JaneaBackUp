#!/usr/bin/env python3
"""Reactivate the gate after the 100-concurrent test's crash wave, verify the Barry fixture,
confirm it stays active. No further burst tests -- ceiling is bracketed (50 safe, 100 unsafe),
pushing further would just cause a 4th instance-strain event for marginal precision gain."""
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
WID = "9aP2dP0jgAPFGDvA"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


n8n(f"/api/v1/workflows/{WID}/activate", "POST", {})
time.sleep(2)
full = n8n(f"/api/v1/workflows/{WID}")
print("active after reactivate:", full.get("active"))

WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"
payload = {"rows": [
    {"label": "known-blocked", "email": "pii-d50f3785@example.invalid"},
    {"label": "known-clean", "email": "final-verify-clean@example.invalid"},
]}
req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        body = json.loads(r.read())
        print("Barry fixture result:", body.get("counts"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code, e.read()[:500])

time.sleep(2)
full = n8n(f"/api/v1/workflows/{WID}")
print("active after fixture check:", full.get("active"))
