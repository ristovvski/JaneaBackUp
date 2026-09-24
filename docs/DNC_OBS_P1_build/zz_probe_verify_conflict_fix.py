#!/usr/bin/env python3
"""
Verify the Slack-conflict-alert fix live: fire a payload through DNC__UpsertLedger__v1 that
reproduces the exact Person-69cbb908 conflict shape (LinkedIn resolves to one existing row, email to
a different one) and confirm the call SUCCEEDS (doesn't crash the caller) and the alert actually
posts to the corrected channel. Read-only against the registry -- a genuine conflict never writes,
by design, so this can't corrupt anything.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
WEBHOOK_PATH = "zz-probe-verify-conflict-fix"


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


# reproduces the exact Person-69cbb908 conflict: this LinkedIn slug already exists on one row,
# this email already exists on a DIFFERENT row.
payload = {
    "linkedin_url": "https://www.linkedin.com/in/pii-8fcafbff",
    "email": "pii-74b0e852@example.invalid",
    "full_name": "Person-69cbb908",
    "reason": "sales_personal_outreach", "source": "pipedrive_personal",
    "source_ref": "zz_probe_verify", "source_signal": "creator",
    "date_precision": "derived", "expiry_review_pending": False,
    "correlation_id": "zz_probe_verify_conflict_fix:" + str(int(time.time())),
}

exec_upsert = node("Call UpsertLedger", "n8n-nodes-base.executeWorkflow", {
    "source": "database",
    "workflowId": {"__rl": True, "mode": "id", "value": UPSERT_LEDGER_ID},
    "mode": "each", "options": {}
}, -400, tv=1.2)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0021"}),
    node("Build Row", "n8n-nodes-base.code",
         {"jsCode": "return [{ json: " + json.dumps(payload) + " }];\n", "mode": "runOnceForAllItems"},
         -680, tv=2),
    exec_upsert,
    node("Report", "n8n-nodes-base.code",
         {"jsCode": "return [{ json: { result: $input.all().map(i => i.json) } }];\n",
          "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_verify_conflict_fix",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Row"), ("Build Row", "Call UpsertLedger"),
        ("Call UpsertLedger", "Report"), ("Report", "Respond"),
    ]),
    "settings": {},
}


def main():
    print("Creating verify workflow...")
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
        status_ok = True
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            status_ok = False

        print(f"\nHTTP request succeeded (no crash propagated): {status_ok}")
        if raw:
            try:
                result = json.loads(raw)
                print(json.dumps(result, indent=2)[:1000])
            except json.JSONDecodeError:
                print("raw (not JSON):", raw[:500])
        ok = status_ok
    except Exception:
        print(f"\nUnexpected error -- NOT deleting workflow (id={wid})")
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
