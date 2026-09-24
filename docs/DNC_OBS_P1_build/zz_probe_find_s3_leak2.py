#!/usr/bin/env python3
"""
Broaden the S3 leak search: ANY registry row carrying a source_signal (creator|surfe|both) --
not just correlation_id prefix s3_creation_watch:* -- since manual backfill fires this session
used other prefixes (s3_scope_widen_backfill:, s3_surfe_backfill:) but wrote the SAME
source_signal field. Cross-check each against the underlying lead's real creator_id/origin.
Read-only.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-find-s3-leak2"
WEBSITE_TOKEN_CREATOR = 13015123


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
    "filters": {"conditions": [{"keyName": "source_signal", "condition": "isNotEmpty"}]},
    "options": {}
}, -400, tv=1)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobes3leak2"}),
    dt_get,
    node("Report", "n8n-nodes-base.code", {
        "jsCode": "return [{ json: { rows: $input.all().map(i => i.json) } }];\n",
        "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_find_s3_leak2",
    "nodes": nodes,
    "connections": conns([("Webhook", "Get All Rows"), ("Get All Rows", "Report"), ("Report", "Respond")]),
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
        rows = result.get("rows", [])
        print(f"\n{len(rows)} rows carry a source_signal (any correlation_id prefix)\n")

        leaked = []
        for row in rows:
            corr = row.get("correlation_id") or ""
            lead_id = corr.split(":", 1)[1] if ":" in corr else None
            lead = {}
            if lead_id and len(lead_id) > 20:  # looks like a real Pipedrive lead uuid
                r2 = requests.get(f"https://api.pipedrive.com/v1/leads/{lead_id}",
                                   params={"api_token": PD_TOKEN}, timeout=20)
                lead = (r2.json() or {}).get("data") or {}
            is_leak = (lead.get("creator_id") == WEBSITE_TOKEN_CREATOR
                       or str(lead.get("origin")).lower() == "api" and lead.get("creator_id") == WEBSITE_TOKEN_CREATOR)
            entry = {
                "row_id": row.get("id"), "identity_key": row.get("identity_key"),
                "full_name": row.get("full_name"), "pipedrive_person_id": row.get("pipedrive_person_id"),
                "source_signal": row.get("source_signal"), "source_ref": row.get("source_ref"),
                "source": row.get("source"), "correlation_id": corr, "lead_id": lead_id,
                "lead_title": lead.get("title"), "lead_creator_id": lead.get("creator_id"),
                "lead_owner_id": lead.get("owner_id"), "lead_origin": lead.get("origin"),
                "lead_channel_id": lead.get("channel_id"),
                "org_name": ((lead.get("organization_id") or {}) if isinstance(lead.get("organization_id"), dict) else {}).get("name"),
            }
            marker = " <<<< WEBSITE-TOKEN CREATOR" if entry["lead_creator_id"] == WEBSITE_TOKEN_CREATOR else ""
            print(f"  row {entry['row_id']} ({entry['full_name']}) creator={entry['lead_creator_id']} "
                  f"owner={entry['lead_owner_id']} origin={entry['lead_origin']} "
                  f"signal={entry['source_signal']} ref={entry['source_ref']}{marker}")
            if entry["lead_creator_id"] == WEBSITE_TOKEN_CREATOR:
                leaked.append(entry)
            time.sleep(0.2)

        with open(os.path.join(HERE, "fixtures", "s3_leak_full_scan.json"), "w", encoding="utf-8") as f:
            json.dump(rows if False else [], f)  # placeholder, real data written below
        with open(os.path.join(HERE, "fixtures", "s3_leak_diagnosis_full.json"), "w", encoding="utf-8") as f:
            json.dump({"total_s3_rows": len(rows), "leaked": leaked}, f, indent=1)
        print(f"\n{len(leaked)} rows leaked from creator {WEBSITE_TOKEN_CREATOR}")
        print(f"wrote fixtures/s3_leak_diagnosis_full.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"cleaned up {wid}")


if __name__ == "__main__":
    main()
