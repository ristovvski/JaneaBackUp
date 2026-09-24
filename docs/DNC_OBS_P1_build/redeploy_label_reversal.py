#!/usr/bin/env python3
"""One-off redeploy of dnc_label_reversal (id LQRfmEl4Wv0qpXsI) after the frozen-id-set fix
(candidate source = auditor's dnc_projection_labelled_1978.json, not a fresh registry scan).
Full nodes/connections replace from the freshly generated JSON, same PUT pattern as
patch_upsert_ledger_slack_cred.py. Already inactive (webhook-triggered dev workflow) -- no
deactivate/reactivate needed.
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UTIL_DIR = os.path.join(os.path.dirname(HERE), "WF1_W1.0.1_build")
sys.path.insert(0, UTIL_DIR)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

WID = "LQRfmEl4Wv0qpXsI"  # dnc_label_reversal
LOCAL_PATH = os.path.join(HERE, "workflows", "dnc_label_reversal", "dnc_label_reversal.json")


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

classify = next((n for n in after["nodes"] if n["name"] == "R Classify"), None)
if classify is None or "frozen_ids" not in classify["parameters"]["jsCode"]:
    print("FAILED -- R Classify does not reference frozen_ids after redeploy")
    sys.exit(1)
cfg = next((n for n in after["nodes"] if n["name"] == "CONFIG"), None)
fire_flag = next((a for a in cfg["parameters"]["assignments"]["assignments"] if a["name"] == "FIRE_REVERSAL"), None)
if not fire_flag or fire_flag["value"] is not False:
    print(f"FAILED -- FIRE_REVERSAL is not false after redeploy: {fire_flag}")
    sys.exit(1)
print("OK -- redeployed with frozen-id-set candidate source, FIRE_REVERSAL confirmed false (dry-run only).")
