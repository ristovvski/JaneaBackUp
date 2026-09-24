#!/usr/bin/env python3
"""Read-only: what the Data Table node's Table > List returns on this instance - in particular,
whether each table carries its size. Throwaway webhook workflow: create, fire once, deactivate,
delete (no incident value). Prints table names, ids, row counts/sizes if present; no row data."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.strip().split("=", 1)
        env[k] = v.strip('"')
ctx = ssl.create_default_context(cafile=env.get("REQUESTS_CA_BUNDLE"))
BASE = env["N8N_BASE_URL"].rstrip("/")
HOOK = "probe-dt-sizes-" + uuid.uuid4().hex[:12]


def n8n(path, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={"X-N8N-API-KEY": env["N8N_API_KEY"],
                                        "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}


wf = {"name": "ZZ_PROBE_datatable_sizes_DELETE_ME", "settings": {"executionOrder": "v1"},
      "nodes": [
          {"parameters": {"httpMethod": "GET", "path": HOOK, "responseMode": "lastNode",
                          "responseData": "allEntries", "options": {}},
           "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
           "position": [0, 0], "webhookId": str(uuid.uuid4())},
          {"parameters": {"resource": os.environ.get("RES", "table"), "operation": os.environ.get("OP", "list"), "returnAll": True, "options": {}},
           "id": "dt", "name": "List Tables", "type": "n8n-nodes-base.dataTable", "typeVersion": float(os.environ.get("TV", "1")),
           "position": [220, 0], "alwaysOutputData": True}],
      "connections": {"Webhook": {"main": [[{"node": "List Tables", "type": "main", "index": 0}]]}}}

wid = n8n("/api/v1/workflows", "POST", wf)["id"]
try:
    n8n("/api/v1/workflows/%s/activate" % wid, "POST", {})
    time.sleep(1.5)
    try:
        with urllib.request.urlopen(BASE.replace("/api/v1", "") + "/webhook/" + HOOK, timeout=90,
                                    context=ctx) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = {"HTTP": e.code, "body": e.read().decode()[:400]}
    print(json.dumps(out, indent=1, ensure_ascii=False)[:6000])
    time.sleep(2)
    ex = n8n("/api/v1/executions?workflowId=%s&includeData=true&limit=1" % wid).get("data", [])
    if ex:
        rd = ex[0].get("data", {}).get("resultData", {})
        print("execution status:", ex[0].get("status"), "| error:", json.dumps(rd.get("error"))[:800])
finally:
    n8n("/api/v1/workflows/%s/deactivate" % wid, "POST", {})
    n8n("/api/v1/workflows/%s" % wid, "DELETE")
    print("probe %s deactivated + deleted" % wid)
