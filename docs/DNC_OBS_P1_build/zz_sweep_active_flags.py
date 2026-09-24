#!/usr/bin/env python3
"""Estate-wide active-flag sweep -- auditor's P2 fix, 2026-08-26: after any instance-level event
(today had at least 3: I-04's own walk crash, the Clay burst, my own 100-concurrent gate test),
sweep ALL workflows for active=false rather than relying on the synthetic monitor probe alone
(which had a documented 29-minute hole today). Read-only. Lists every workflow with its active
status, flags production-pattern-named ones that are currently inactive as review candidates."""
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

PROD_PREFIXES = ("dnc_", "WF1_", "WF-", "WF2", "heyreach_", "smartlead_", "I04", "dnc_i04")
KNOWN_NEVER_ACTIVE = {"dnc_pre_add_gate", "DEV__dnc_pre_add_gate"}  # webhook-triggered, active=True expected actually -- keep in report, not excluded


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x)


all_wf = []
cursor = None
while True:
    path = "/api/v1/workflows?limit=250"
    if cursor:
        path += f"&cursor={cursor}"
    page = n8n(path)
    all_wf.extend(page.get("data", []))
    cursor = page.get("nextCursor")
    if not cursor:
        break

print(f"total workflows: {len(all_wf)}\n")

zz_probes = [w for w in all_wf if w["name"].startswith("zz_")]
prod = [w for w in all_wf if not w["name"].startswith("zz_")]

print(f"zz_probe/throwaway workflows still present: {len(zz_probes)}")
for w in zz_probes:
    print(f"  {'ACTIVE' if w.get('active') else 'inactive'}  {w['id']}  {w['name']}")

print(f"\nnon-probe workflows: {len(prod)}")
inactive_prod_pattern = []
for w in sorted(prod, key=lambda w: w["name"]):
    status = "ACTIVE" if w.get("active") else "inactive"
    print(f"  {status}  {w['id']}  {w['name']}")
    if not w.get("active") and w["name"].startswith(PROD_PREFIXES):
        inactive_prod_pattern.append(w)

print(f"\n{'='*60}")
print(f"INACTIVE workflows matching production-name patterns ({len(inactive_prod_pattern)}):")
for w in inactive_prod_pattern:
    print(f"  {w['id']}  {w['name']}")
