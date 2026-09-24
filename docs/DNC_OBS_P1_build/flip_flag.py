#!/usr/bin/env python3
"""One-off live PATCH of a single boolean CONFIG assignment on an already-deployed workflow --
never baked into the generator. Usage: python flip_flag.py <workflow_id> <flag_name> <true|false>
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UTIL_DIR = os.path.join(os.path.dirname(HERE), "WF1_W1.0.1_build")
sys.path.insert(0, UTIL_DIR)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

WID = sys.argv[1]
FLAG = sys.argv[2]
NEW_VALUE = sys.argv[3].lower() == "true"


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


wf = n8n(f"/api/v1/workflows/{WID}")
cfg = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
a = next(x for x in cfg["parameters"]["assignments"]["assignments"] if x["name"] == FLAG)
print(f"before: {FLAG} = {a['value']}")
a["value"] = NEW_VALUE

dropped = stripped_keys(wf)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")

n8n(f"/api/v1/workflows/{WID}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WID}")
cfg2 = next(n for n in after["nodes"] if n["name"] == "CONFIG")
a2 = next(x for x in cfg2["parameters"]["assignments"]["assignments"] if x["name"] == FLAG)
print(f"after:  {FLAG} = {a2['value']} (versionId {after.get('versionId')})")
if a2["value"] != NEW_VALUE:
    print("FAILED -- flag did not take the new value")
    sys.exit(1)
print("OK")
