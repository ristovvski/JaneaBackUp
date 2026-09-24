#!/usr/bin/env python3
"""Throwaway, read-only connectivity + row-count probe for the Supabase project (credential id
u6wyGnYC71Sr1KgT, native n8n Supabase credential type "supabaseApi", named "Supabase account").
Deploys a tiny isolated webhook-triggered workflow that does GET requests against Supabase's
PostgREST (count-only via Prefer: count=exact + limit=0 -- no row data ever pulled, no table
mutated), fires it once per table, prints results, then deletes the probe workflow. Does not touch
any existing workflow or any n8n Data Table."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

SUPABASE_URL = "https://icxrjwccqitqmpypwhie.supabase.co"
CRED_ID = "u6wyGnYC71Sr1KgT"
CRED_NAME = "Supabase account"
TABLES = {"dnc_domains": "domain"}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def build():
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": "probe-supabase-connectivity",
                         "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 300], "webhookId": "probesupabaseconn02"},
        {"parameters": {
            "method": "GET",
            "url": "={{ '" + SUPABASE_URL + "/rest/v1/' + $json.query.table + '?select=' + $json.query.col + '&limit=1' }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            # forces PostgREST to answer as a SINGLE object, not an array -- this makes a
            # genuinely-empty-but-accessible table answer with its own specific, informative error
            # ("JSON object requested, multiple (or no) rows returned", PGRST116) instead of a
            # silently-empty array that n8n's HTTP node then collapses to zero output items,
            # indistinguishable from a swallowed permission error.
            "headerParameters": {"parameters": [{"name": "Accept", "value": "application/vnd.pgrst.object+json"}]},
            "options": {"fullResponse": True},
         },
         "id": "probe", "name": "Probe Count", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [-200, 300],
         "credentials": {"supabaseApi": {"id": CRED_ID, "name": CRED_NAME}},
         "onError": "continueErrorOutput"},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Probe Count", "type": "main", "index": 0}]]},
        "Probe Count": {"main": [[{"node": "Respond", "type": "main", "index": 0}],
                                  [{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return {"name": "ZZ_PROBE_supabase_connectivity_DELETE_ME", "nodes": nodes,
            "connections": connections, "settings": {}}


def fire(path, query):
    url = BASE.replace("/api/v1", "") + "/webhook/" + path + "?" + query
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (raw.decode() if raw else None)


def main():
    wf_json = build()
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    print(f"deployed probe workflow id={wid}")
    time.sleep(1)

    try:
        for t, col in TABLES.items():
            status, body = fire("probe-supabase-connectivity", f"table={t}&col={col}")
            if isinstance(body, dict) and "error" in body:
                print(f"[{t}] HTTP {status} -> ERROR: {json.dumps(body['error'])[:300]}")
                continue
            print(f"[{t}] HTTP {status} -> OK: {json.dumps(body)[:2000]}")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"probe workflow {wid} deactivated + deleted (throwaway, no incident value).")


if __name__ == "__main__":
    main()
