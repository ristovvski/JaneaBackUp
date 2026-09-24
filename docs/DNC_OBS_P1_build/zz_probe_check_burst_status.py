#!/usr/bin/env python3
"""Check whether the Clay burst is still ongoing right now before touching the live gate
workflow -- last 20 executions, timestamps, current active status."""
import json, os, ssl

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
import urllib.request
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WID = "9aP2dP0jgAPFGDvA"


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


full = n8n(f"/api/v1/workflows/{WID}")
print("active:", full.get("active"))
execs = n8n(f"/api/v1/executions?workflowId={WID}&limit=20")
for e in execs.get("data", []):
    print(e.get("startedAt"), e.get("stoppedAt"), e.get("status"))
