#!/usr/bin/env python3
"""Deploy dnc_gate_queue_drainer as a new workflow, INACTIVE -- needs dnc_gate_queue to exist
before it does anything useful, and needs its own real table-id fix (same as EVENT_LOG_TABLE)
once that table exists."""
import json, os, ssl, urllib.error, urllib.request

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
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


path = os.path.join(HERE, "workflows", "dnc_gate_queue_drainer", "dnc_gate_queue_drainer.json")
with open(path, encoding="utf-8") as f:
    wf_json = json.load(f)

page = n8n("/api/v1/workflows?limit=250")
existing = next((w for w in page.get("data", []) if w.get("name") == wf_json["name"]), None)
if existing:
    wid = existing["id"]
    n8n(f"/api/v1/workflows/{wid}", "PUT",
        {"name": wf_json["name"], "nodes": wf_json["nodes"],
         "connections": wf_json["connections"], "settings": wf_json["settings"]})
    print(f"updated {wf_json['name']} id={wid}")
else:
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created {wf_json['name']} id={wid}")
live = n8n(f"/api/v1/workflows/{wid}")
print(f"active={live.get('active')} nodes={len(live.get('nodes', []))}")
