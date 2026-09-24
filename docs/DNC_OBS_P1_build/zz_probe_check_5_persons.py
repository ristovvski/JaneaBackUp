#!/usr/bin/env python3
"""
Check dnc_registry_dev for 5 person_ids (85766, 85767, 85769, 85772, 85774) -- this week's
genuine roster-human creations per Auditor's sweep (Leadjet x3, UI x2), which found zero field-686
(Pipedrive DNC projection) writes for them. Read-only.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-check-5-persons"
PERSON_IDS = [85766, 85767, 85769, 85772, 85774]


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


build_items_js = "return " + json.dumps(PERSON_IDS) + ".map(pid => ({ json: { pid } }));\n"

dt_get = node("Check Registry", "n8n-nodes-base.dataTable", {
    "resource": "row", "operation": "get",
    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
    "matchType": "allConditions",
    "filters": {"conditions": [{"keyName": "pipedrive_person_id", "condition": "eq",
                                  "keyValue": "={{ $json.pid }}"}]},
    "options": {}
}, -400, tv=1)

report_js = (
    "return $input.all().map(i => ({ json: i.json }));\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0014"}),
    node("Build Items", "n8n-nodes-base.code", {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         -680, tv=2),
    dt_get,
    node("Report", "n8n-nodes-base.code",
         {"jsCode": "return [{ json: { rows: $input.all().map(i => i.json) } }];\n",
          "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_check_5_persons",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Items"),
        ("Build Items", "Check Registry"),
        ("Check Registry", "Report"),
        ("Report", "Respond"),
    ]),
    "settings": {},
}


def main():
    print("Creating probe workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")

    ok = False
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE -- aborting")
            sys.exit(1)

        webhook_url = BASE + "/webhook/" + WEBHOOK_PATH
        time.sleep(2)
        req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        raw = b""
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()

        result = json.loads(raw)
        print("\n=== REGISTRY CHECK (85766, 85767, 85769, 85772, 85774) ===")
        found_pids = {r.get("pipedrive_person_id") for r in result.get("rows", [])}
        for pid in PERSON_IDS:
            if pid in found_pids:
                row = next(r for r in result["rows"] if r.get("pipedrive_person_id") == pid)
                print(f"  {pid}: IN REGISTRY -- reason={row.get('reason')} entry_type={row.get('entry_type')} "
                      f"source_signal={row.get('source_signal')} source={row.get('source')} "
                      f"projections_state={row.get('projections_state')}")
            else:
                print(f"  {pid}: NOT IN REGISTRY")
        ok = True
    except Exception:
        print(f"\nUnexpected error -- NOT deleting probe workflow (id={wid})")
        try:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        except Exception:
            pass
        raise

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"\ndeleted probe workflow {wid}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
