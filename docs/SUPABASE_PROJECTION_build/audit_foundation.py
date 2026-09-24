#!/usr/bin/env python3
"""Read-only DNC full audit -- foundation pull (2026-09-15).
Deploys ONE throwaway probe workflow with 4 independent webhook entry points (each its own
linear chain, no fan-in), fires each once, tears the workflow down. Writes raw dumps + a
summary report to audit_out/. No table is ever written to.
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

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
REGISTRY_TABLE = "UOgKwlGsL28lX61O"
DOMAINS_TABLE = "ai4ZiOGqzuJHRYLB"
CLAIMS_TABLE = "euyostwJYfJefItC"

OUT_DIR = os.path.join(HERE, "audit_out")
os.makedirs(OUT_DIR, exist_ok=True)


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def fire(path, timeout=120):
    url = BASE.replace("/api/v1", "") + "/webhook/" + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def build():
    nodes = [
        # --- registry dump ---
        {"parameters": {"httpMethod": "GET", "path": "audit-get-registry", "responseMode": "responseNode", "options": {}},
         "id": "wh_reg", "name": "WH Registry", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 0], "webhookId": "auditgetregistry01"},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": REGISTRY_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_reg", "name": "Get Registry", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-200, 0], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"respondWith": "allIncomingItems", "options": {}}, "id": "resp_reg", "name": "Respond Registry",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 0]},

        # --- domains dump ---
        {"parameters": {"httpMethod": "GET", "path": "audit-get-domains", "responseMode": "responseNode", "options": {}},
         "id": "wh_dom", "name": "WH Domains", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 200], "webhookId": "auditgetdomains01"},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": DOMAINS_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_dom", "name": "Get Domains", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-200, 200], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"respondWith": "allIncomingItems", "options": {}}, "id": "resp_dom", "name": "Respond Domains",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 200]},

        # --- claims dump (whole table, current queue) ---
        {"parameters": {"httpMethod": "GET", "path": "audit-get-claims", "responseMode": "responseNode", "options": {}},
         "id": "wh_cl", "name": "WH Claims", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 400], "webhookId": "auditgetclaims01"},
        {"parameters": {"resource": "row", "operation": "getAll",
                         "dataTableId": {"__rl": True, "mode": "id", "value": CLAIMS_TABLE},
                         "returnAll": True, "options": {}},
         "id": "get_cl", "name": "Get Claims", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-200, 400], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"respondWith": "allIncomingItems", "options": {}}, "id": "resp_cl", "name": "Respond Claims",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 400]},

        # --- generic supabase proxy: ?path=<rest path incl querystring after /rest/v1/> ---
        {"parameters": {"httpMethod": "GET", "path": "audit-supabase", "responseMode": "responseNode", "options": {}},
         "id": "wh_sb", "name": "WH Supabase", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 600], "webhookId": "auditsupabase01"},
        {"parameters": {
            "method": "GET",
            "url": "={{ '" + SUPABASE_URL + "/rest/v1/' + $json.query.p }}",
            "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Prefer", "value": "count=exact"}]},
            "options": {"response": {"response": {"fullResponse": True}}},
         }, "id": "sb_probe", "name": "Supabase Probe", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": [-200, 600], "credentials": {"supabaseApi": {"id": CRED_ID, "name": CRED_NAME}},
         "onError": "continueErrorOutput"},
        {"parameters": {"options": {}}, "id": "resp_sb", "name": "Respond Supabase",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 600]},
    ]
    connections = {
        "WH Registry": {"main": [[{"node": "Get Registry", "type": "main", "index": 0}]]},
        "Get Registry": {"main": [[{"node": "Respond Registry", "type": "main", "index": 0}]]},
        "WH Domains": {"main": [[{"node": "Get Domains", "type": "main", "index": 0}]]},
        "Get Domains": {"main": [[{"node": "Respond Domains", "type": "main", "index": 0}]]},
        "WH Claims": {"main": [[{"node": "Get Claims", "type": "main", "index": 0}]]},
        "Get Claims": {"main": [[{"node": "Respond Claims", "type": "main", "index": 0}]]},
        "WH Supabase": {"main": [[{"node": "Supabase Probe", "type": "main", "index": 0}]]},
        "Supabase Probe": {"main": [[{"node": "Respond Supabase", "type": "main", "index": 0}],
                                     [{"node": "Respond Supabase", "type": "main", "index": 0}]]},
    }
    return {"name": "ZZ_AUDIT_20260915_foundation_DELETE_ME", "nodes": nodes, "connections": connections, "settings": {}}


def supabase_get(path_and_qs):
    status, body = fire("audit-supabase?p=" + urllib.request.quote(path_and_qs, safe=""), timeout=90)
    return status, body


def paginate_supabase(table, select="*", extra_qs="", page_size=1000):
    rows = []
    offset = 0
    total = None
    while True:
        qs = f"{table}?select={select}&offset={offset}&limit={page_size}"
        if extra_qs:
            qs += "&" + extra_qs
        status, body = supabase_get(qs)
        if not isinstance(body, dict):
            print(f"  WARNING non-dict response at offset {offset}: {str(body)[:200]}")
            break
        headers = body.get("headers", {})
        cr = headers.get("content-range")
        if cr and total is None:
            try:
                total = int(cr.split("/")[-1])
            except Exception:
                pass
        page = body.get("body")
        if not isinstance(page, list):
            print(f"  WARNING page at offset {offset} not a list: {str(page)[:300]}")
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows, total


def main():
    print("deploying foundation probe workflow...")
    wf = build()
    created = n8n("/api/v1/workflows", "POST", wf)
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    print(f"deployed id={wid}")
    time.sleep(1.5)

    try:
        print("fetching n8n registry (full)...")
        status, registry = fire("audit-get-registry", timeout=150)
        print(f"  status={status} rows={len(registry) if isinstance(registry, list) else 'ERR:' + str(registry)[:200]}")

        print("fetching n8n domains (full)...")
        status, domains = fire("audit-get-domains", timeout=90)
        print(f"  status={status} rows={len(domains) if isinstance(domains, list) else 'ERR:' + str(domains)[:200]}")

        print("fetching n8n claims (full, current queue)...")
        status, claims = fire("audit-get-claims", timeout=60)
        print(f"  status={status} rows={len(claims) if isinstance(claims, list) else 'ERR:' + str(claims)[:200]}")

        print("fetching Supabase registry (paginated)...")
        sb_registry, sb_reg_total = paginate_supabase("dnc_registry")
        print(f"  fetched={len(sb_registry)} content-range-total={sb_reg_total}")

        print("fetching Supabase domains (paginated)...")
        sb_domains, sb_dom_total = paginate_supabase("dnc_domains")
        print(f"  fetched={len(sb_domains)} content-range-total={sb_dom_total}")

        print("fetching Supabase dnc_registry_meta (last 20 rows)...")
        status, meta_body = supabase_get("dnc_registry_meta?select=*&order=last_sync_at.desc&limit=20")
        meta_rows = meta_body.get("body") if isinstance(meta_body, dict) else None
        print(f"  status={status} rows={len(meta_rows) if isinstance(meta_rows, list) else meta_rows}")

        # persist raw dumps
        with open(os.path.join(OUT_DIR, "n8n_registry.json"), "w", encoding="utf-8") as f:
            json.dump(registry, f)
        with open(os.path.join(OUT_DIR, "n8n_domains.json"), "w", encoding="utf-8") as f:
            json.dump(domains, f)
        with open(os.path.join(OUT_DIR, "n8n_claims.json"), "w", encoding="utf-8") as f:
            json.dump(claims, f)
        with open(os.path.join(OUT_DIR, "supabase_registry.json"), "w", encoding="utf-8") as f:
            json.dump(sb_registry, f)
        with open(os.path.join(OUT_DIR, "supabase_domains.json"), "w", encoding="utf-8") as f:
            json.dump(sb_domains, f)
        with open(os.path.join(OUT_DIR, "supabase_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta_rows, f)

        print("\nRAW DUMPS WRITTEN to audit_out/. Summary:")
        print(f"  n8n registry rows:      {len(registry) if isinstance(registry, list) else 'ERROR'}")
        print(f"  supabase registry rows: {len(sb_registry)} (Content-Range total {sb_reg_total})")
        print(f"  n8n domains rows:       {len(domains) if isinstance(domains, list) else 'ERROR'}")
        print(f"  supabase domains rows:  {len(sb_domains)} (Content-Range total {sb_dom_total})")
        print(f"  n8n claims rows (current queue): {len(claims) if isinstance(claims, list) else 'ERROR'}")
        print(f"  supabase meta rows fetched: {len(meta_rows) if isinstance(meta_rows, list) else 'ERROR'}")

    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"probe workflow {wid} deactivated + deleted.")


if __name__ == "__main__":
    main()
