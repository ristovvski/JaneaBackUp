#!/usr/bin/env python3
"""
S3 leak diagnosis: find every dnc_registry_dev row written by the live creation watcher
(correlation_id starting with 's3_creation_watch:'), then for each, fetch the underlying
Pipedrive lead to check its ACTUAL creator_id/origin -- the registry row itself only stores
source_signal/source_ref, not the lead's raw creator_id, so this requires a live cross-check.
Read-only.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-find-s3-leak"


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
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"), "name": name,
         "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def conns(pairs):
    c = {}
    for a, b in pairs:
        c.setdefault(a, {"main": [[]]})
        c[a]["main"][0].append({"node": b, "type": "main", "index": 0})
    return c


dt_get = node("Get All Rows", "n8n-nodes-base.dataTable", {
    "resource": "row", "operation": "get",
    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
    "returnAll": True, "matchType": "allConditions",
    "filters": {"conditions": [{"keyName": "correlation_id", "condition": "isNotEmpty"}]},
    "options": {}
}, -400, tv=1)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobes3leak1"}),
    dt_get,
    node("Filter S3", "n8n-nodes-base.code", {
        "jsCode": (
            "const rows = $input.all().map(i => i.json);\n"
            "const s3rows = rows.filter(r => (r.correlation_id || '').startsWith('s3_creation_watch:'));\n"
            "return [{ json: { s3rows } }];\n"
        ), "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_find_s3_leak",
    "nodes": nodes,
    "connections": conns([("Webhook", "Get All Rows"), ("Get All Rows", "Filter S3"), ("Filter S3", "Respond")]),
    "settings": {},
}


def main():
    print("Creating probe workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")

    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE")
            sys.exit(1)
        time.sleep(2)
        req = urllib.request.Request(BASE + "/webhook/" + WEBHOOK_PATH, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
            result = json.loads(r.read())
        s3rows = result.get("s3rows", [])
        print(f"\n{len(s3rows)} rows written by the live S3 watcher (correlation_id s3_creation_watch:*)\n")

        out = []
        for row in s3rows:
            corr = row["correlation_id"]
            lead_id = corr.split("s3_creation_watch:", 1)[1]
            r2 = requests.get(f"https://api.pipedrive.com/v1/leads/{lead_id}",
                               params={"api_token": PD_TOKEN}, timeout=20)
            lead = (r2.json() or {}).get("data") or {}
            entry = {
                "row_id": row.get("id"), "identity_key": row.get("identity_key"),
                "full_name": row.get("full_name"), "pipedrive_person_id": row.get("pipedrive_person_id"),
                "source_signal": row.get("source_signal"), "source_ref": row.get("source_ref"),
                "correlation_id": corr, "lead_id": lead_id,
                "lead_title": lead.get("title"), "lead_creator_id": lead.get("creator_id"),
                "lead_owner_id": lead.get("owner_id"), "lead_origin": lead.get("origin"),
                "lead_channel_id": lead.get("channel_id"),
            }
            out.append(entry)
            print(f"  row {entry['row_id']} ({entry['full_name']}) lead={lead_id[:8]} "
                  f"creator={entry['lead_creator_id']} owner={entry['lead_owner_id']} "
                  f"origin={entry['lead_origin']} channel={entry['lead_channel_id']} "
                  f"signal={entry['source_signal']} ref={entry['source_ref']}")
            time.sleep(0.2)

        with open(os.path.join(HERE, "fixtures", "s3_leak_diagnosis.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(f"\nwrote fixtures/s3_leak_diagnosis.json ({len(out)} rows)")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"cleaned up {wid}")


if __name__ == "__main__":
    main()
