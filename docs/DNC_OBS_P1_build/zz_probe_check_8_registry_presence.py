#!/usr/bin/env python3
"""
Throwaway probe: for each of the 8 sales-roster leads found in fixtures/s3_roster_leads_since_live.json,
check whether pipedrive_person_id already has an active row in dnc_registry_dev. Read-only.
Needed to compute the accurate blind-spot count for the pre-post (Nik: "report the blind-spot
count in the pre-post -- that number tells us how big the hole was") -- NOT all 8 are necessarily
missing; Noah (in the OLD 5-roster) + Surfe signal on 6 of them means most were likely already
caught, and only Dennis (new-roster addition) + Ken/Maria (separately diagnosed misses) are
confirmed gaps so far.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-check-8-presence"


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


with open(os.path.join(HERE, "fixtures", "s3_roster_leads_since_live.json"), encoding="utf-8") as f:
    candidates = json.load(f)

build_items_js = "return " + json.dumps(candidates) + ".map(c => ({ json: c }));\n"

# no alwaysOutputData -- a true non-match must yield ZERO items, not a null-filled placeholder
# (the exact false-positive caught earlier this session on the Ken/Maria diagnostic).
dt_get = node("Check Registry", "n8n-nodes-base.dataTable", {
    "resource": "row", "operation": "get",
    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
    "matchType": "allConditions",
    "filters": {"conditions": [{"keyName": "pipedrive_person_id", "condition": "eq",
                                  "keyValue": "={{ $json.person_id }}"}]},
    "options": {}
}, -400, tv=1)

report_js = (
    "const found = new Set($input.all().map(i => i.json.pipedrive_person_id));\n"
    "return [{ json: { found: [...found] } }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0008"}),
    node("Build Items", "n8n-nodes-base.code", {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         -680, tv=2),
    dt_get,
    node("Report", "n8n-nodes-base.code", {"jsCode": report_js, "mode": "runOnceForAllItems"}, -200, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 0),
]

wf_json = {
    "name": "zz_probe_check_8_registry_presence",
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
        found_ids = set(result.get("found", []))
        print("\n=== PRESENCE CHECK (8 sales-roster leads since S3 went live) ===")
        for c in candidates:
            status = "ALREADY IN REGISTRY" if c["person_id"] in found_ids else "MISSING"
            print(f"  {c['title']:35s} pid={c['person_id']:<8} {status}")
        missing = [c for c in candidates if c["person_id"] not in found_ids]
        print(f"\n{len(missing)}/{len(candidates)} missing from the registry.")
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
