#!/usr/bin/env python3
"""One-off redeploy of dnc_s4_event_populations (id hhdnug5xdFLAxrOg). Found live 2026-08-14 while
resuming the S4 build: the deployed workflow still had the webhook-body/chunk_size fixes but NOT
the Smartlead campaign/leads shape fix (row.lead nesting) -- would have produced all-null normalized
fields on the very next fire. Full nodes/connections replace from the freshly generated JSON, same
PUT pattern as redeploy_label_reversal.py / patch_upsert_ledger_slack_cred.py.
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UTIL_DIR = os.path.join(os.path.dirname(HERE), "WF1_W1.0.1_build")
sys.path.insert(0, UTIL_DIR)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

WID = "hhdnug5xdFLAxrOg"  # dnc_s4_event_populations
LOCAL_PATH = os.path.join(HERE, "workflows", "dnc_s4_event_populations", "dnc_s4_event_populations.json")


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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:1200]}")
        raise


before = n8n(f"/api/v1/workflows/{WID}")
print(f"before: active={before.get('active')} versionId={before.get('versionId')} nodes={len(before.get('nodes') or [])}")

local = json.load(open(LOCAL_PATH, encoding="utf-8"))
merged = dict(before)
merged["nodes"] = local["nodes"]
merged["connections"] = local["connections"]

dropped = stripped_keys(merged)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")

n8n(f"/api/v1/workflows/{WID}", "PUT", put_body(merged))
after = n8n(f"/api/v1/workflows/{WID}")
print(f"after:  active={after.get('active')} versionId={after.get('versionId')} nodes={len(after.get('nodes') or [])}")

norm = next((n for n in after["nodes"] if n["name"] == "S4 Normalize Smartlead"), None)
if norm is None or "row.lead || {}" not in norm["parameters"]["jsCode"]:
    print("FAILED -- S4 Normalize Smartlead does not have the .lead shape fix after redeploy")
    sys.exit(1)
cfg = next((n for n in after["nodes"] if n["name"] == "CONFIG"), None)
fire_flag = next((a for a in cfg["parameters"]["assignments"]["assignments"] if a["name"] == "FIRE_S4"), None)
if not fire_flag or fire_flag["value"] is not False:
    print(f"FAILED -- FIRE_S4 is not false after redeploy: {fire_flag}")
    sys.exit(1)
print("OK -- redeployed with the Smartlead shape fix, FIRE_S4 confirmed false (dry-run only).")
