#!/usr/bin/env python3
"""Post-verify Phase 2 step 1: exact counts, 50-row field-by-field sample on dnc_registry, full
1,373-row compare on dnc_domains. Redesigned after the first version overloaded n8n by returning
the full 25,729-row registry TWICE in one workflow response (caused transient 502/503s) -- this
version fetches the n8n side exactly ONCE (kept in Python memory), and every Supabase-side webhook
call stays small (counts, a 50-row sample, or the 1,373-row domains table -- never the registry
in full)."""
import json
import os
import random
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
REGISTRY_TABLE = "UOgKwlGsL28lX61O"
DOMAINS_TABLE = "ai4ZiOGqzuJHRYLB"

REGISTRY_COLUMNS = [
    "id", "identity_key", "norm_v", "linkedin_url_norm", "email_lc", "full_name",
    "pipedrive_person_id", "entry_type", "reason", "source", "source_ref", "source_signal",
    "correlation_id", "date_precision", "expiry_review_pending", "offboard_removable",
    "also_flagged", "projections_state", "owner_tag", "status", "added_at", "removed_at",
    "removed_reason", "reply_category", "expires_at", "createdAt", "updatedAt",
]
TS_COLUMNS = {"added_at", "removed_at", "expires_at", "createdAt", "updatedAt"}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def fire(path, timeout=60):
    url = BASE.replace("/api/v1", "") + "/webhook/" + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (raw.decode() if raw else None)


def deploy_probe(nodes, connections, name):
    wf_json = {"name": name, "nodes": nodes, "connections": connections, "settings": {}}
    created = n8n("/api/v1/workflows", "POST", wf_json)
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    return wid


def cleanup(wid):
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")


def supabase_http_node(x, y, url_expr, extra_headers=None):
    return {"parameters": {
        "method": "GET", "url": url_expr,
        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
        "sendHeaders": bool(extra_headers), "headerParameters": {"parameters": extra_headers or []},
        # httpRequest typeVersion 4.2's real path for "full response" is nested under
        # options.response.response.fullResponse -- a flat options.fullResponse is silently
        # ignored (confirmed live: it just returned the parsed/autodetected body with no wrapper).
        "options": {"response": {"response": {"fullResponse": True}}},
    }, "id": "probe", "name": "Probe", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "position": [x, y], "credentials": {"supabaseApi": {"id": CRED_ID, "name": CRED_NAME}},
        "onError": "continueErrorOutput"}


def single_supabase_call(webhook_path, url_expr, extra_headers=None):
    """Deploys a minimal Webhook -> Probe -> Respond workflow, fires it once, tears it down."""
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": webhook_path, "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-400, 300], "webhookId": webhook_path.replace("-", "") + "01"},
        supabase_http_node(-200, 300, url_expr, extra_headers),
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Probe", "type": "main", "index": 0}]]},
        "Probe": {"main": [[{"node": "Respond", "type": "main", "index": 0}], [{"node": "Respond", "type": "main", "index": 0}]]},
    }
    wid = deploy_probe(nodes, connections, f"ZZ_PROBE_{webhook_path}_DELETE_ME")
    time.sleep(1)
    try:
        return fire(webhook_path, timeout=90)
    finally:
        cleanup(wid)


def deploy_full_export():
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": "probe-full-export-v2", "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-600, 300], "webhookId": "probefullexportv201"},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": REGISTRY_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_registry", "name": "Get Registry", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 200], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": DOMAINS_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_domains", "name": "Get Domains", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 400], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"jsCode": (
            "return [{ json: {\n"
            "  registry: $('Get Registry').all().map(i => i.json),\n"
            "  domains: $('Get Domains').all().map(i => i.json),\n"
            "} }];\n"), "mode": "runOnceForAllItems"},
         "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [-200, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Get Registry", "type": "main", "index": 0},
                               {"node": "Get Domains", "type": "main", "index": 0}]]},
        "Get Registry": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Get Domains": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return deploy_probe(nodes, connections, "ZZ_PROBE_full_export_v2_DELETE_ME")


def fetch_n8n_source():
    wid = deploy_full_export()
    time.sleep(1)
    try:
        status, body = fire("probe-full-export-v2", timeout=120)
        return body["registry"], body["domains"]
    finally:
        cleanup(wid)


def norm_ts(v):
    # canonicalizes to a comparable instant -- PostgREST returns "+00:00" (and trims trailing
    # zero fractional-second digits, e.g. ".51" for ".510"), n8n's dataTable returns "Z" with full
    # millisecond padding; both encode the exact same instant.
    if v is None:
        return None
    from datetime import datetime
    v2 = v.replace("Z", "+00:00")
    return datetime.fromisoformat(v2).isoformat()


def main():
    print("fetching n8n source (registry + domains) once...")
    registry_rows, domain_rows = fetch_n8n_source()
    print(f"n8n: registry={len(registry_rows)} domains={len(domain_rows)}")

    # 1) exact counts via Prefer: count=exact (Content-Range header, e.g. "0-0/25729")
    status, body = single_supabase_call(
        "pv-count-registry", SUPABASE_URL + "/rest/v1/dnc_registry?select=id&limit=1",
        [{"name": "Prefer", "value": "count=exact"}])
    reg_count_hdr = (body or {}).get("headers", {}).get("content-range")
    status, body = single_supabase_call(
        "pv-count-domains", SUPABASE_URL + "/rest/v1/dnc_domains?select=domain&limit=1",
        [{"name": "Prefer", "value": "count=exact"}])
    dom_count_hdr = (body or {}).get("headers", {}).get("content-range")

    reg_supabase_total = int(reg_count_hdr.split("/")[-1]) if reg_count_hdr else None
    dom_supabase_total = int(dom_count_hdr.split("/")[-1]) if dom_count_hdr else None
    print(f"\nCOUNTS: registry n8n={len(registry_rows)} supabase={reg_supabase_total} "
          f"{'MATCH' if reg_supabase_total == len(registry_rows) else 'MISMATCH'}")
    print(f"        domains  n8n={len(domain_rows)} supabase={dom_supabase_total} "
          f"{'MATCH' if dom_supabase_total == len(domain_rows) else 'MISMATCH'}")

    # 2) 50-row field-by-field sample on registry
    random.seed(42)
    sample = random.sample(registry_rows, min(50, len(registry_rows)))
    ids_str = ",".join(str(r["id"]) for r in sample)
    status, body = single_supabase_call(
        "pv-sample-registry", SUPABASE_URL + "/rest/v1/dnc_registry?select=*&id=in.(" + ids_str + ")")
    sup_rows = (body or {}).get("body")
    sup_by_id = {r["id"]: r for r in sup_rows} if isinstance(sup_rows, list) else {}
    print(f"\nREGISTRY SAMPLE: {len(sample)} requested, {len(sup_by_id)} found in Supabase")
    mismatches = []
    for n_row in sample:
        s_row = sup_by_id.get(n_row["id"])
        if not s_row:
            mismatches.append((n_row["id"], "MISSING in Supabase"))
            continue
        for col in REGISTRY_COLUMNS:
            nv, sv = n_row.get(col), s_row.get(col)
            if col in TS_COLUMNS:
                nv, sv = norm_ts(nv), norm_ts(sv)
            if nv != sv:
                mismatches.append((n_row["id"], col, nv, sv))
    print(f"field mismatches: {len(mismatches)}")
    for m in mismatches[:20]:
        print("  ", m)

    # 3) all 1,373 domains compared -- PAGINATED: Supabase/PostgREST's default max-rows caps any
    # single response at 1000 regardless of the requested limit, confirmed live (first attempt
    # silently returned only 1000 of 1373 rows, looking exactly like 373 "missing" rows).
    sup_dom_by_key = {}
    offset = 0
    page_size = 1000
    while offset < dom_supabase_total:
        status, body = single_supabase_call(
            "pv-all-domains", SUPABASE_URL + f"/rest/v1/dnc_domains?select=*&offset={offset}&limit={page_size}")
        page = (body or {}).get("body")
        if not isinstance(page, list):
            print(f"  WARNING: domains page at offset {offset} returned non-list: {page}")
            break
        sup_dom_by_key.update({r["domain"]: r for r in page})
        offset += page_size
    n8n_dom_by_key = {r["domain"]: r for r in domain_rows}
    missing = [d for d in n8n_dom_by_key if d not in sup_dom_by_key]
    extra = [d for d in sup_dom_by_key if d not in n8n_dom_by_key]
    dom_mismatches = []
    for d, n_row in n8n_dom_by_key.items():
        s_row = sup_dom_by_key.get(d)
        if not s_row:
            continue
        for col in ("domain", "source", "reason", "status"):
            if (n_row.get(col) or None) != (s_row.get(col) or None):
                dom_mismatches.append((d, col, n_row.get(col), s_row.get(col)))
        if norm_ts(n_row.get("added_at")) != norm_ts(s_row.get("added_at")):
            dom_mismatches.append((d, "added_at", n_row.get("added_at"), s_row.get("added_at")))
    print(f"\nDOMAINS: n8n={len(n8n_dom_by_key)} supabase={len(sup_dom_by_key)} "
          f"missing={len(missing)} extra={len(extra)} field_mismatches={len(dom_mismatches)}")
    if missing:
        print("  missing:", missing[:10])
    if extra:
        print("  extra:", extra[:10])
    for m in dom_mismatches[:20]:
        print("  ", m)

    print("\nDONE")


if __name__ == "__main__":
    main()
