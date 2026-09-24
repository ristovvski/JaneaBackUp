#!/usr/bin/env python3
"""Fire the Person-69cbb908 known-blocked fixture + a clean fixture against the live gate webhook,
confirm the classify split is correct, then re-check active status hasn't flipped back off."""
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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


payload = {"rows": [
    {"label": "known-blocked", "email": "pii-d50f3785@example.invalid"},
    {"label": "known-clean", "email": "verify-clean-probe-abc@example.invalid"},
]}
req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}",
                              method="POST", data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        result = json.loads(r.read())
    print("gate response:", json.dumps(result, indent=2)[:2000])
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code, e.read()[:500])

time.sleep(3)
check = n8n(f"/api/v1/workflows/{WID}")
print("active after test fire:", check.get("active"))
