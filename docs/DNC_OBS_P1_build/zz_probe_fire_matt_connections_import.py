#!/usr/bin/env python3
"""
Fires fixtures/matt_carothers_connections_writable.json (1,491 rows) through the real
DNC__UpsertLedger__v1, chunked (100/chunk), via one throwaway webhook-triggered workflow deployed
once, fired N times, then deactivated+deleted -- same zz_probe_ discipline as every other one-off
this project. Resumable: writes progress to a local cursor file so a crash mid-run doesn't replay
already-written chunks.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
WEBHOOK_PATH = "zz-probe-matt-connections-import"
CHUNK_SIZE = 100
CURSOR_PATH = os.path.join(HERE, "_matt_import_cursor.json")
ROWS_PATH = os.path.join(HERE, "fixtures", "matt_carothers_connections_writable.json")


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


with open(ROWS_PATH, encoding="utf-8") as f:
    ALL_ROWS = json.load(f)
# strip the review-only fields, keep only what UpsertLedger's prep_js reads
CLEAN_ROWS = [{k: v for k, v in r.items() if not k.startswith("_")} for r in ALL_ROWS]

build_items_js = "return $input.first().json.body.rows.map(r => ({ json: r }));\n"

exec_upsert = node("Call UpsertLedger", "n8n-nodes-base.executeWorkflow", {
    "source": "database",
    "workflowId": {"__rl": True, "mode": "id", "value": UPSERT_LEDGER_ID},
    "mode": "each", "options": {}
}, -400, tv=1.2)

report_js = (
    "const results = $input.all().map(i => i.json);\n"
    "const byAction = {};\n"
    "for (const r of results) { const a = r.action || 'unknown'; byAction[a] = (byAction[a]||0)+1; }\n"
    "return [{ json: { count: results.length, by_action: byAction } }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0010"}),
    node("Build Items", "n8n-nodes-base.code", {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         -680, tv=2),
    exec_upsert,
    node("Report", "n8n-nodes-base.code", {"jsCode": report_js, "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_fire_matt_connections_import",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Items"),
        ("Build Items", "Call UpsertLedger"),
        ("Call UpsertLedger", "Report"),
        ("Report", "Respond"),
    ]),
    "settings": {},
}


def load_cursor():
    if os.path.exists(CURSOR_PATH):
        with open(CURSOR_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"offset": 0, "wid": None, "totals": {}}


def save_cursor(c):
    with open(CURSOR_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f)


def main():
    cursor = load_cursor()
    wid = cursor.get("wid")

    if not wid:
        print("Creating chunk-fire workflow...")
        created = n8n("/api/v1/workflows", "POST",
                      {"name": wf_json["name"], "nodes": wf_json["nodes"],
                       "connections": wf_json["connections"], "settings": wf_json["settings"]})
        wid = created["id"]
        cursor["wid"] = wid
        save_cursor(cursor)
        print(f"created id={wid}")
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE -- aborting")
            sys.exit(1)
        time.sleep(2)
    else:
        print(f"resuming existing workflow id={wid} from offset={cursor['offset']}")

    webhook_url = BASE + "/webhook/" + WEBHOOK_PATH
    totals = cursor.get("totals", {})
    total_rows = len(CLEAN_ROWS)

    try:
        while cursor["offset"] < total_rows:
            chunk = CLEAN_ROWS[cursor["offset"]: cursor["offset"] + CHUNK_SIZE]
            req = urllib.request.Request(webhook_url, method="POST",
                                          data=json.dumps({"rows": chunk}).encode(),
                                          headers={"Content-Type": "application/json"})
            raw = b""
            try:
                with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                    raw = r.read()
            except urllib.error.HTTPError as e:
                raw = e.read()
                print(f"\nHTTP error on chunk at offset {cursor['offset']}: {raw[:500]!r}")
                sys.exit(2)

            result = json.loads(raw)
            for k, v in (result.get("by_action") or {}).items():
                totals[k] = totals.get(k, 0) + v
            cursor["offset"] += len(chunk)
            cursor["totals"] = totals
            save_cursor(cursor)
            print(f"  chunk done: offset={cursor['offset']}/{total_rows}  this-chunk={result.get('count')}  "
                  f"running-totals={totals}")
    except Exception:
        print(f"\nUnexpected error -- workflow id={wid} left ACTIVE, cursor saved at offset={cursor['offset']} "
              f"for resume. NOT deleting.")
        raise

    print(f"\n=== DONE: {cursor['offset']}/{total_rows} rows fired ===")
    print(json.dumps(totals, indent=2))

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    if os.path.exists(CURSOR_PATH):
        os.remove(CURSOR_PATH)
    print(f"deleted probe workflow {wid}, cleaned up cursor")


if __name__ == "__main__":
    main()
