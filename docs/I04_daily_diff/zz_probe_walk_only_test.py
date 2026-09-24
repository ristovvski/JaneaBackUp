#!/usr/bin/env python3
"""Test JUST the walk (leads + persons, full live estate) + build-snapshot logic, with no
Data Table dependency at all (i04_snapshots doesn't exist yet -- needs a UI create first). This
validates the highest-risk, most-uncertain part (full-estate native pagination + flatten +
build, ~58k leads) works without OOM/timeout before the table exists to test the rest against.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_i04 import (node, conns, code_node, set_config, http_pipedrive_offset,  # noqa: E402
                        http_pipedrive_cursor, OPS_CHANNEL, TELEMETRY_CHANNEL, LH_KEY, DNC_FIELD,
                        DNC_ACTIVE, DNC_LABEL)

ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


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


walk_leads_js = (
    "const pages = $input.all().map(i => i.json);\n"
    "const leads = pages.flatMap(p => Array.isArray(p.data) ? p.data : []);\n"
    "const L = {};\n"
    "for (const x of leads) { L[x.id] = [(x.label_ids || []).slice().sort().join('|'), x.person_id, x.add_time]; }\n"
    "const dncLabelled = leads.filter(x => (x.label_ids || []).includes('%s')).map(x => x.id).sort();\n"
    "return [{ json: { lead_count: Object.keys(L).length, pages: pages.length, dnc_labelled_count: dncLabelled.length } }];\n"
) % DNC_LABEL
walk_persons_js = (
    "const pages = $input.all().map(i => i.json);\n"
    "const persons = pages.flatMap(p => Array.isArray(p.data) ? p.data : []);\n"
    "let dncCount = 0, sampleCf = null;\n"
    "for (const p of persons) {\n"
    "  const cf = p.custom_fields || {};\n"
    "  if (!sampleCf) sampleCf = Object.keys(cf).slice(0, 5);\n"
    "  if (cf['%s'] === '%s') dncCount++;\n"
    "}\n"
    "return [{ json: { person_count: persons.length, pages: pages.length, dnc686_count: dncCount, sample_cf_keys: sampleCf } }];\n"
) % (DNC_FIELD, DNC_ACTIVE)

nodes = [
    # onReceived, not responseNode -- a synchronous wait-for-Respond webhook call hits Cloudflare's
    # ~100-120s front-end timeout (524) long before a multi-minute full-estate walk finishes. This
    # is a TEST-METHODOLOGY constraint only -- the real production trigger is a schedule, not a
    # webhook, so no HTTP client is ever waiting on it. Ack immediately, poll executions instead.
    node("Trigger", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "i04-walk-only-test", "responseMode": "onReceived", "options": {}},
         -900, extra={"webhookId": "i04walkonly02"}),
    set_config([("x", "1", "string")], -700),
    http_pipedrive_offset("Walk Leads Page", "=https://api.pipedrive.com/v1/leads?limit=100", -500),
    code_node("Walk Leads Reduce", walk_leads_js, -300),
    http_pipedrive_cursor("Walk Persons Page", "=https://api.pipedrive.com/api/v2/persons?limit=100", -500, y=200),
    code_node("Walk Persons Reduce", walk_persons_js, -300, y=200),
    node("Merge", "n8n-nodes-base.merge", {"mode": "combine", "combineBy": "combineByPosition", "options": {}}, -100, tv=3),
    code_node("Report", "return [{ json: Object.assign({}, $input.all()[0].json, $input.all()[1] ? $input.all()[1].json : {}) }];\n", 100),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 300),
]
connections = conns([
    ("Trigger", "CONFIG"), ("CONFIG", "Walk Leads Page"), ("CONFIG", "Walk Persons Page"),
    ("Walk Leads Page", "Walk Leads Reduce"), ("Walk Persons Page", "Walk Persons Reduce"),
    ("Report", "Respond"),
])
connections["Walk Leads Reduce"] = {"main": [[{"node": "Merge", "type": "main", "index": 0}]]}
connections["Walk Persons Reduce"] = {"main": [[{"node": "Merge", "type": "main", "index": 1}]]}
connections["Merge"] = {"main": [[{"node": "Report", "type": "main", "index": 0}]]}

wf_json = {"name": "zz_probe_walk_only_test", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    print("Creating walk-only test workflow...")
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
        print("Firing (full ~58k-lead + persons walk, expect a few minutes; onReceived -- acks instantly)...")
        t0 = time.time()
        req = urllib.request.Request(BASE + "/webhook/i04-walk-only-test", method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                print(f"webhook ack: {r.status}")
        except urllib.error.HTTPError as e:
            print(f"webhook error: {e.code} {e.read()[:300]}")

        print("polling for execution completion (up to 20 min)...")
        exec_id = None
        for _ in range(120):
            time.sleep(10)
            execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
            data = execs.get("data") or []
            if not data:
                continue
            e = data[0]
            exec_id = e["id"]
            status = e.get("status")
            print(f"  [{time.time()-t0:.0f}s] execution {exec_id}: {status}")
            if status in ("success", "error", "crashed"):
                break
        else:
            print("TIMED OUT after 20 min -- leaving workflow active for manual inspection")
            print(f"workflow id: {wid} (NOT deleted)")
            return

        detail = n8n(f"/api/v1/executions/{exec_id}?includeData=true")
        d = detail.get("data", {})
        err = d.get("resultData", {}).get("error")
        run = d.get("resultData", {}).get("runData", {})
        print(f"\nnodes that ran: {list(run.keys())}")
        if err:
            print(f"\nERROR: {json.dumps(err)[:1500]}")
        if "Report" in run:
            print(f"\nREPORT: {json.dumps(run['Report'][0]['data']['main'][0][0]['json'], indent=1)}")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"cleaned up {wid}")


if __name__ == "__main__":
    main()
