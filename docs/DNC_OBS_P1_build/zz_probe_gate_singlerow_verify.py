#!/usr/bin/env python3
"""Verify the top-level convenience field fix using the EXACT single-row shape Clay's per-row
column sends: one CLEAN case (using a real email from Stefan's CSV that fired but came back
empty) and the known BLOCKED fixture."""
import json, os, ssl, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"


def fire(rows):
    payload = {"rows": rows}
    req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


print("=== single-row CLEAN (real email from Stefan's CSV, previously empty in Clay) ===")
r1 = fire([{"email": "pii-39036e6d@example.invalid"}])
print("top-level gate_result:", r1.get("gate_result"))
print("top-level reason:", r1.get("reason"))
print("counts:", r1.get("counts"))

print("\n=== single-row BLOCKED (Barry/Dennis fixture) ===")
r2 = fire([{"email": "pii-d50f3785@example.invalid"}])
print("top-level gate_result:", r2.get("gate_result"))
print("top-level reason:", r2.get("reason"))
print("top-level registry_row_ref:", r2.get("registry_row_ref"))
print("counts:", r2.get("counts"))

print("\n=== batch call (2 rows) -- top-level fields must be ABSENT, batch fields unchanged ===")
r3 = fire([{"email": "pii-39036e6d@example.invalid"}, {"email": "pii-d50f3785@example.invalid"}])
print("top-level gate_result present:", "gate_result" in r3)
print("counts:", r3.get("counts"))
