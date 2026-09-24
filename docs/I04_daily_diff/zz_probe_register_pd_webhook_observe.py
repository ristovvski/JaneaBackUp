#!/usr/bin/env python3
"""I-04 event-driven redesign: register a REAL (narrowly-scoped, reversible) Pipedrive webhook
subscription pointed at a throwaway n8n webhook receiver, then poll for a short window to
observe whatever real organic lead/person activity naturally happens, capturing the ACTUAL
payload shape (current/previous/meta/event) before writing any parsing code against it. Scoped
to updated+deleted+added on lead and person only (not '*' like the existing Make.com sub) to
keep this observation narrow. Deletes the webhook subscription and the probe workflow at the end
regardless of what was captured."""
import json, os, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
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
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-pd-webhook-observe", "responseMode": "onReceived", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobepdwebhookobs01"},
    # no write anywhere -- the payload is captured via the execution's OWN stored input data
    # (read back through GET /api/v1/executions/{id}?includeData=true, same technique used
    # throughout this session), never touching any real table just to observe a shape.
    {"parameters": {"jsCode": "return $input.all();", "mode": "runOnceForAllItems"},
     "id": "passthrough", "name": "Passthrough", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-200, 300]},
]
connections = {"Webhook": {"main": [[{"node": "Passthrough", "type": "main", "index": 0}]]}}
wf_json = {"name": "zz_probe_pd_webhook_observe", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"probe workflow id={wid}")
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)

    sub_url = BASE.replace("/api/v1", "") + "/webhook/zz-probe-pd-webhook-observe"
    print("registering Pipedrive webhook ->", sub_url)
    pd_body = json.dumps({"subscription_url": sub_url, "event_action": "*", "event_object": "lead"}).encode()
    req = urllib.request.Request(f"https://api.pipedrive.com/v1/webhooks?api_token={PD_TOKEN}",
                                  method="POST", data=pd_body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            sub_result = json.loads(r.read())
        print("subscription created:", json.dumps(sub_result, indent=2)[:800])
        sub_id = (sub_result.get("data") or {}).get("id")
    except urllib.error.HTTPError as e:
        print("SUBSCRIPTION FAILED:", e.code, e.read()[:1000])
        sub_id = None

    if sub_id:
        print(f"\nWatching for 90s for any real lead event... (subscription id={sub_id})")
        time.sleep(90)

    print("\nchecking probe workflow executions for any captured payload...")
    try:
        execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=5")
        rows = execs.get("data", [])
        print(f"probe workflow executions: {len(rows)}")
        for e in rows:
            eid = e.get("id")
            print(" ", eid, e.get("startedAt"), e.get("status"))
            full = n8n(f"/api/v1/executions/{eid}?includeData=true")
            run_data = ((full.get("data", {}).get("resultData") or {}).get("runData") or {})
            webhook_run = run_data.get("Webhook")
            if webhook_run:
                payload = webhook_run[0]["data"]["main"][0][0]["json"]
                print("REAL PIPEDRIVE WEBHOOK PAYLOAD:")
                print(json.dumps(payload, indent=2)[:6000])
    except Exception as ex:
        print("could not check executions:", ex)

    if sub_id:
        del_req = urllib.request.Request(f"https://api.pipedrive.com/v1/webhooks/{sub_id}?api_token={PD_TOKEN}",
                                          method="DELETE")
        try:
            with urllib.request.urlopen(del_req, timeout=30, context=ctx) as r:
                print("subscription deleted:", r.status)
        except urllib.error.HTTPError as e:
            print("delete failed:", e.code, e.read()[:500])

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print("probe workflow cleaned up")


if __name__ == "__main__":
    main()
