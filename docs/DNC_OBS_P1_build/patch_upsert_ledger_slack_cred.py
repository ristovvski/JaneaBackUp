#!/usr/bin/env python3
"""Fix DNC__UpsertLedger__v1's placeholder Slack credential so the zz_probe_ verification can
actually execute. n8n's CredentialsPermissionChecker validates EVERY credential referenced
anywhere in a workflow before running it -- even on branches the input won't take -- so the
"Slack Conflict Alert" node's placeholder id="REPLACE_ME" blocks the whole workflow, including
the plain-insert path the probe needs.

Already inactive -- no deactivate/reactivate needed, just PUT.
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UTIL_DIR = os.path.join(os.path.dirname(HERE), "WF1_W1.0.1_build")
sys.path.insert(0, UTIL_DIR)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

WID = "gD9aBaNjwslZMD0S"  # DNC__UpsertLedger__v1
REAL_SLACK_CRED = {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}


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
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:900]}")
        raise


wf = n8n(f"/api/v1/workflows/{WID}")
print(f"before: active={wf.get('active')} versionId={wf.get('versionId')}")

fixed = 0
for n in wf["nodes"]:
    creds = n.get("credentials") or {}
    if "slackApi" in creds and creds["slackApi"].get("id") == "REPLACE_ME":
        print(f"  patching {n['name']}: {creds['slackApi']} -> {REAL_SLACK_CRED}")
        n["credentials"]["slackApi"] = REAL_SLACK_CRED
        fixed += 1

if fixed == 0:
    print("nothing to patch (no REPLACE_ME slackApi refs found) -- exiting without a PUT")
    sys.exit(0)

dropped = stripped_keys(wf)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")

n8n(f"/api/v1/workflows/{WID}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WID}")
print(f"after:  active={after.get('active')} versionId={after.get('versionId')}")

still_broken = [n["name"] for n in after["nodes"]
                if (n.get("credentials") or {}).get("slackApi", {}).get("id") == "REPLACE_ME"]
if still_broken:
    print(f"FAILED -- still REPLACE_ME on: {still_broken}")
    sys.exit(1)
if after.get("active") is not False:
    print(f"WARNING: workflow is active={after.get('active')} after PUT (expected False)")
    sys.exit(1)
print(f"OK -- {fixed} node(s) patched, workflow confirmed inactive, versionId is now {after.get('versionId')}")
