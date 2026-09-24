#!/usr/bin/env python3
"""
Count the split-identity class: employee_connection rows with no pipedrive_person_id and no
email (LinkedIn-only, e.g. Noah's Aug-11 import) that have a plausible pid-carrying counterpart
elsewhere in the registry (name/slug corroboration, same rule as dncSplitIdentityMergeV1).
Read-only.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request, re

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-count-split-class"


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


get_emp = node("Get Employee Connections", "n8n-nodes-base.dataTable", {
    "resource": "row", "operation": "get",
    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
    "returnAll": True, "matchType": "allConditions",
    "filters": {"conditions": [{"keyName": "entry_type", "condition": "eq", "keyValue": "employee_connection"}]},
    "options": {}
}, -600, tv=1)

get_pid = node("Get Pid-Carrying", "n8n-nodes-base.dataTable", {
    "resource": "row", "operation": "get",
    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
    "returnAll": True, "matchType": "allConditions",
    "filters": {"conditions": [{"keyName": "pipedrive_person_id", "condition": "isNotEmpty"}]},
    "options": {}
}, -600, y=200, tv=1)

merge = node("Merge", "n8n-nodes-base.merge", {"mode": "combine", "combineBy": "combineByPosition",
                                                "options": {}}, -300, tv=3)

report_js = (
    "function slugify(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }\n"
    "const empItems = $('Get Employee Connections').all().map(i => i.json);\n"
    "const pidItems = $('Get Pid-Carrying').all().map(i => i.json);\n"
    "const liOnly = empItems.filter(r => r.pipedrive_person_id == null && r.email_lc == null && r.linkedin_url_norm != null);\n"
    "const byPidId = new Set(pidItems.map(r => r.id));\n"
    "const matches = [];\n"
    "for (const emp of liOnly) {\n"
    "  const empSlug = slugify(emp.full_name) || String(emp.identity_key || '').toLowerCase().replace(/[^a-z0-9]/g, '');\n"
    "  for (const pid of pidItems) {\n"
    "    if (byPidId.has(emp.id)) continue;\n"  # emp row itself never carries a pid, redundant guard
    "    const pidSlug = slugify(pid.full_name);\n"
    "    if (pidSlug && empSlug && pidSlug === empSlug) {\n"
    "      matches.push({ emp_id: emp.id, emp_identity_key: emp.identity_key, emp_full_name: emp.full_name,\n"
    "        pid_id: pid.id, pid_full_name: pid.full_name, pid_person_id: pid.pipedrive_person_id });\n"
    "      break;\n"
    "    }\n"
    "  }\n"
    "}\n"
    "return [{ json: { total_employee_connection: empItems.length, li_only_no_pid_no_email: liOnly.length,\n"
    "  total_pid_carrying: pidItems.length, matched_split_identity_pairs: matches.length, matches } }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0023"}),
    get_emp,
    get_pid,
    node("Report", "n8n-nodes-base.code", {"jsCode": report_js, "mode": "runOnceForAllItems"}, 0, tv=2),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 300),
]

wf_json = {
    "name": "zz_probe_count_split_identity_class",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Get Employee Connections"), ("Webhook", "Get Pid-Carrying"),
        ("Get Employee Connections", "Report"), ("Get Pid-Carrying", "Report"),
        ("Report", "Respond"),
    ]),
    "settings": {},
}


def main():
    print("Creating count workflow...")
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
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()

        result = json.loads(raw)
        print("\n=== SPLIT-IDENTITY CLASS COUNT ===")
        print(f"total employee_connection rows: {result.get('total_employee_connection')}")
        print(f"LinkedIn-only, no pid, no email: {result.get('li_only_no_pid_no_email')}")
        print(f"total pid-carrying rows: {result.get('total_pid_carrying')}")
        print(f"matched split-identity pairs: {result.get('matched_split_identity_pairs')}")
        for m in result.get("matches", []):
            print(f"  emp_id={m['emp_id']} ({m['emp_full_name'] or m['emp_identity_key']}) <-> "
                  f"pid_id={m['pid_id']} pid={m['pid_person_id']} ({m['pid_full_name']})")
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
