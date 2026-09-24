#!/usr/bin/env python3
"""Generic one-off redeploy: full nodes/connections replace from the freshly generated local JSON,
same PUT pattern as redeploy_label_reversal.py / redeploy_s4.py. Usage:
  python redeploy_generic.py <workflow_id> <workflow_dir_name>
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UTIL_DIR = os.path.join(os.path.dirname(HERE), "WF1_W1.0.1_build")
sys.path.insert(0, UTIL_DIR)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

WID = sys.argv[1]
WF_DIR = sys.argv[2]
LOCAL_PATH = os.path.join(HERE, "workflows", WF_DIR, f"{WF_DIR}.json")


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
