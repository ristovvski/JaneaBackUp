#!/usr/bin/env python3
"""Isolated, read-only probe: does $('AncestorNode').item.json.field correctly resolve PER-ITEM
through a chain where an intermediate node replaces $json entirely (like an HTTP node does)? This
is the exact mechanism dnc_supabase_delta_pusher's "Delete Claim" node depends on. No real table or
workflow touched -- pure in-memory item routing test."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": "probe-paired-item", "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1, "position": [-800, 300],
         "webhookId": "probepaireditem01"},
        {"parameters": {"jsCode": "return [{json:{tag:'A'}},{json:{tag:'B'}},{json:{tag:'C'}}];", "mode": "runOnceForAllItems"},
         "id": "make3", "name": "Make 3 Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-600, 300]},
        {"parameters": {"jsCode": "return { json: { tag: $json.tag } };", "mode": "runOnceForEachItem"},
         "id": "tagit", "name": "Tag It", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-400, 300]},
        # simulates an HTTP node replacing $json entirely with an unrelated response shape.
        {"parameters": {"jsCode": "return { json: { statusCode: 200, unrelated: Math.random() } };", "mode": "runOnceForEachItem"},
         "id": "replace", "name": "Simulate HTTP Replace", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-200, 300]},
        {"parameters": {"jsCode": "return { json: { recovered_tag: $('Tag It').item.json.tag } };", "mode": "runOnceForEachItem"},
         "id": "recover", "name": "Recover Via Named Ref", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
        {"parameters": {"jsCode": "return [{ json: { results: $input.all().map(i => i.json) } }];", "mode": "runOnceForAllItems"},
         "id": "collect", "name": "Collect", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond", "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Make 3 Items", "type": "main", "index": 0}]]},
        "Make 3 Items": {"main": [[{"node": "Tag It", "type": "main", "index": 0}]]},
        "Tag It": {"main": [[{"node": "Simulate HTTP Replace", "type": "main", "index": 0}]]},
        "Simulate HTTP Replace": {"main": [[{"node": "Recover Via Named Ref", "type": "main", "index": 0}]]},
        "Recover Via Named Ref": {"main": [[{"node": "Collect", "type": "main", "index": 0}]]},
        "Collect": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    wf_json = {"name": "ZZ_PROBE_paired_item_DELETE_ME", "nodes": nodes, "connections": connections, "settings": {}}
    created = n8n("/api/v1/workflows", "POST", wf_json)
    wid = created["id"]
    print("workflow id:", wid)
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    try:
        url = BASE.replace("/api/v1", "") + "/webhook/probe-paired-item"
        req = urllib.request.Request(url, method="GET")
        body = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                    body = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 404 and attempt < 2:
                    time.sleep(2)
                    continue
                raise
        print(json.dumps(body, indent=2))
        results = body["results"]
        ok = [r["recovered_tag"] for r in results] == ["A", "B", "C"]
        print("\nPER-ITEM PAIRING", "CONFIRMED CORRECT" if ok else "*** BROKEN -- DO NOT TRUST .item ACROSS THIS CHAIN SHAPE ***")
    finally:
        try:
            execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=3&includeData=true")
            for e in execs.get("data", []):
                print("execution", e["id"], e.get("status"), e.get("data", {}).get("resultData", {}).get("error"))
        except Exception as diag_err:
            print("diag failed:", diag_err)
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("probe cleaned up")


if __name__ == "__main__":
    main()
