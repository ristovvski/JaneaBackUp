#!/usr/bin/env python3
"""
S3 scope-widening backfill -- the 3 confirmed registry gaps (verified live via
zz_probe_check_8_registry_presence.py, deleted after use): Person-ea6fcf66, Person-83a8d74b,
Person-b0fb1597. Nik's GO (2026-08-19): "3 rows, trivial" -- pre-post already sent to
#niks-channel BEFORE this fire.

Calls the REAL, already-deployed DNC__UpsertLedger__v1 (id RolYGL3J2CNg6Yp3) for each row --
same production write path S3's own watcher uses, not a shortcut around it. Throwaway webhook
wrapper, deleted after firing per this project's zz_probe_ discipline.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
WEBHOOK_PATH = "zz-probe-s3-backfill-3"


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


ROWS = [
    {
        "linkedin_url": "https://www.linkedin.com/in/pii-04f50952/",
        "email": "pii-d50f3785@example.invalid",
        "full_name": "Person-ea6fcf66",
        "pipedrive_person_id": 85772,
        "reason": "sales_personal_outreach", "source": "pipedrive_personal",
        "source_ref": "Slava Kraievskyi", "source_signal": "creator",
        "date_precision": "derived", "expiry_review_pending": False,
        "correlation_id": "s3_scope_widen_backfill:a6eefe70-9bc1-11f1-b556-6daff5f4ffe9",
    },
    {
        "linkedin_url": "https://linkedin.com/in/pii-34b598ce",
        "email": "pii-ad37e19c@example.invalid",
        "full_name": "Person-83a8d74b",
        "pipedrive_person_id": 85767,
        "reason": "sales_personal_outreach", "source": "pipedrive_personal",
        "source_ref": "Noah Keimach", "source_signal": "both",
        "date_precision": "derived", "expiry_review_pending": False,
        "correlation_id": "s3_scope_widen_backfill:b5f38160-980c-11f1-b664-d5433d6cf8ac",
    },
    {
        "linkedin_url": "https://linkedin.com/in/pii-4ed9ce03",
        "email": None,
        "full_name": "Person-b0fb1597",
        "pipedrive_person_id": 85761,
        "reason": "sales_personal_outreach", "source": "pipedrive_personal",
        "source_ref": "Noah Keimach", "source_signal": "both",
        "date_precision": "derived", "expiry_review_pending": False,
        "correlation_id": "s3_scope_widen_backfill:a8fca300-9682-11f1-b6d6-19031bcb002c",
    },
]

build_items_js = "return " + json.dumps(ROWS) + ".map(r => ({ json: r }));\n"

exec_upsert = node("Call UpsertLedger", "n8n-nodes-base.executeWorkflow", {
    "source": "database",
    "workflowId": {"__rl": True, "mode": "id", "value": UPSERT_LEDGER_ID},
    "mode": "each", "options": {}
}, -400, tv=1.2)

report_js = (
    "return [{ json: { results: $input.all().map(i => i.json) } }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0009"}),
    node("Build Rows", "n8n-nodes-base.code", {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         -680, tv=2),
    exec_upsert,
    node("Report", "n8n-nodes-base.code", {"jsCode": report_js, "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_s3_scope_widen_backfill_3",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Rows"),
        ("Build Rows", "Call UpsertLedger"),
        ("Call UpsertLedger", "Report"),
        ("Report", "Respond"),
    ]),
    "settings": {},
}


def main():
    print("Creating backfill workflow...")
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
        print("\n=== BACKFILL RESULT ===")
        print(json.dumps(result, indent=2))
        ok = True
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
