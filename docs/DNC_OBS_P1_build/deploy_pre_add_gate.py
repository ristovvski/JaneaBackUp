#!/usr/bin/env python3
"""Deploy dnc_pre_add_gate (or its DEV__ sandbox twin) as a NEW workflow, active immediately --
matches the create-then-verify pattern used throughout this project. Usage:
  python deploy_pre_add_gate.py dev    # deploys DEV__dnc_pre_add_gate
  python deploy_pre_add_gate.py live   # deploys dnc_pre_add_gate
"""
import json, os, ssl, sys, urllib.error, urllib.request

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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if which == "dev":
        path = os.path.join(HERE, "workflows", "DEV__dnc_pre_add_gate", "DEV__dnc_pre_add_gate.json")
    else:
        path = os.path.join(HERE, "workflows", "dnc_pre_add_gate", "dnc_pre_add_gate.json")

    with open(path, encoding="utf-8") as f:
        wf_json = json.load(f)

    print(f"Creating {wf_json['name']}...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    live = n8n(f"/api/v1/workflows/{wid}")
    print(f"active={live.get('active')} nodes={len(live.get('nodes', []))}")
    print(wid)


if __name__ == "__main__":
    main()
