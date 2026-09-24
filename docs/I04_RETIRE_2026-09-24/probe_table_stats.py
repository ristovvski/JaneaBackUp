#!/usr/bin/env python3
"""Read-only: per data table, row count, serialized bytes, and rows created in the last 1/7/30 days.
One throwaway webhook workflow (dataTable get returnAll -> Code aggregate -> respond), fired once
per table, then deactivated + deleted. Returns AGGREGATES only - no row content leaves n8n.

Serialized bytes = JSON length of every row as n8n returns it. It is NOT n8n's storage figure (that
is database pages + indexes, visible only in the UI); it is the estimate the digest can compute."""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
env = {}
for line in open(os.path.join(os.path.dirname(HERE), ".env"), encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.strip().split("=", 1)
        env[k] = v.strip('"')
ctx = ssl.create_default_context(cafile=env.get("REQUESTS_CA_BUNDLE"))
BASE = env["N8N_BASE_URL"].rstrip("/")
HOOK = "probe-dt-stats-" + uuid.uuid4().hex[:12]

AGG = r"""
const rows = $input.all().map(i => i.json).filter(r => r && Object.keys(r).length);
const errored = rows.filter(r => r.error !== undefined);
const now = Date.now(), D = 86400000;
let bytes = 0, d1 = 0, d7 = 0, d30 = 0, maxId = 0, oldest = null;
for (const r of rows) {
  bytes += Buffer.byteLength(JSON.stringify(r), 'utf8');
  const t = Date.parse(r.createdAt || '');
  if (!isNaN(t)) {
    if (now - t < D) d1++; if (now - t < 7 * D) d7++; if (now - t < 30 * D) d30++;
    if (oldest === null || t < oldest) oldest = t;
  }
  if (Number(r.id) > maxId) maxId = Number(r.id);
}
return [{json: {rows: rows.length - errored.length, errored: errored.length,
  first_error: errored.length ? String(errored[0].error).slice(0, 160) : null,
  bytes, new_1d: d1, new_7d: d7, new_30d: d30, max_id: maxId,
  oldest: oldest ? new Date(oldest).toISOString().slice(0, 10) : null,
  columns: rows.length ? Object.keys(rows[0]).length : null}}];
"""


def n8n(path, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={"X-N8N-API-KEY": env["N8N_API_KEY"],
                                        "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}


def wf(mode, value):
    return {"name": "ZZ_PROBE_datatable_stats_DELETE_ME", "settings": {"executionOrder": "v1"},
            "nodes": [
                {"parameters": {"httpMethod": "GET", "path": HOOK, "responseMode": "lastNode", "options": {}},
                 "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
                 "position": [0, 0], "webhookId": str(uuid.uuid4())},
                {"parameters": {"resource": "row", "operation": "get", "returnAll": True,
                                "dataTableId": {"__rl": True, "mode": mode, "value": value}},
                 "id": "dt", "name": "Read", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
                 "position": [220, 0], "alwaysOutputData": True, "onError": "continueRegularOutput"},
                {"parameters": {"jsCode": AGG}, "id": "agg", "name": "Agg", "type": "n8n-nodes-base.code",
                 "typeVersion": 2, "position": [440, 0]}],
            "connections": {"Webhook": {"main": [[{"node": "Read", "type": "main", "index": 0}]]},
                            "Read": {"main": [[{"node": "Agg", "type": "main", "index": 0}]]}}}


tables = json.load(open(os.path.join(HERE, "table_ids.json")))
results = {}
for t in tables:
    wid = n8n("/api/v1/workflows", "POST", wf(t["mode"], t["id"]))["id"]
    try:
        n8n("/api/v1/workflows/%s/activate" % wid, "POST", {})
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(BASE.replace("/api/v1", "") + "/webhook/" + HOOK, timeout=300,
                                        context=ctx) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            out = {"HTTP": e.code, "body": e.read().decode()[:200]}
    finally:
        n8n("/api/v1/workflows/%s/deactivate" % wid, "POST", {})
        n8n("/api/v1/workflows/%s" % wid, "DELETE")
    results[t["id"]] = out
    o = out if isinstance(out, dict) else {}
    print("%-20s rows=%-6s bytes=%-10s MB=%-6s new 1d/7d/30d=%s/%s/%s oldest=%s err=%s" % (
        t["id"], o.get("rows"), o.get("bytes"),
        round(o["bytes"] / 1e6, 2) if isinstance(o.get("bytes"), int) else "?",
        o.get("new_1d"), o.get("new_7d"), o.get("new_30d"), o.get("oldest"),
        (o.get("first_error") or o.get("body") or "")[:90]), flush=True)
json.dump(results, open(os.path.join(HERE, "table_stats_2026-09-24.json"), "w"), indent=1)
