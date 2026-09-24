#!/usr/bin/env python3
import json, os, ssl, sys, urllib.request

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
EID = sys.argv[1]


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


d = n8n(f"/api/v1/executions/{EID}?includeData=true")
data = d.get("data", {})
rd = (data.get("resultData") or {})
print("error:", json.dumps(rd.get("error"), indent=2)[:3000])
run_data = rd.get("runData") or {}
print("nodes that ran:", list(run_data.keys()))
for nname, runs in run_data.items():
    for run in runs:
        if run.get("error"):
            print(f"--- {nname} error ---")
            print(json.dumps(run["error"], indent=2)[:2000])
