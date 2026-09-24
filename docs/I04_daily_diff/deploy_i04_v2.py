#!/usr/bin/env python3
"""Deploy the three I-04 v2 workflows as NEW workflows, INACTIVE (deliberately -- today already
had 3 instance-strain events; activation is a separate, deliberate step after Nik reviews and the
new tables exist). Usage: python deploy_i04_v2.py [dev|live]
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
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x) if x.length != 0 else {}
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")
        raise


def deploy(name):
    path = os.path.join(HERE, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        wf_json = json.load(f)
    page = n8n("/api/v1/workflows?limit=250")
    existing = next((w for w in page.get("data", []) if w.get("name") == wf_json["name"]), None)
    if existing:
        wid = existing["id"]
        print(f"updating existing {wf_json['name']} id={wid}")
        n8n(f"/api/v1/workflows/{wid}", "PUT",
            {"name": wf_json["name"], "nodes": wf_json["nodes"],
             "connections": wf_json["connections"], "settings": wf_json["settings"]})
    else:
        created = n8n("/api/v1/workflows", "POST",
                      {"name": wf_json["name"], "nodes": wf_json["nodes"],
                       "connections": wf_json["connections"], "settings": wf_json["settings"]})
        wid = created["id"]
        print(f"created {wf_json['name']} id={wid}")
    # deliberately NOT activating
    live = n8n(f"/api/v1/workflows/{wid}")
    print(f"  active={live.get('active')} nodes={len(live.get('nodes', []))}")
    return wid


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    prefix = "DEV__" if which == "dev" else ""
    ids = {}
    for base in ["dnc_i04_event_receiver", "dnc_i04_daily_summary", "dnc_i04_weekly_reconciliation"]:
        ids[base] = deploy(f"{prefix}{base}")
    print(json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
