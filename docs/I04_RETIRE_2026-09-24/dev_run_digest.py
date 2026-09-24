#!/usr/bin/env python3
"""Live run of the PATCHED digest graph without posting anything.

DEV__dnc_morning_digest = dnc_morning_digest.post.json with the schedule trigger swapped for a webhook
(same node name, so every reference still resolves) and Post Digest removed: Send Guard is the last
node and its output - the composed Slack text - is the webhook response. Every read the real digest
makes (Smartlead, HeyReach, Pipedrive, n8n, data tables, Supabase) runs for real; nothing is written
and nothing is posted. The copy is deactivated afterwards and KEPT (inactive) as the DEV copy.
"""
import copy
import json
import os
import ssl
import time
import urllib.error
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
HOOK = "dev-digest-" + uuid.uuid4().hex[:12]


def n8n(path, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={"X-N8N-API-KEY": env["N8N_API_KEY"],
                                        "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}


post = json.load(open(os.path.join(HERE, "dnc_morning_digest.post.json"), encoding="utf-8"))
dev = {"name": "DEV__dnc_morning_digest", "settings": {"executionOrder": "v1"},
       "nodes": [], "connections": copy.deepcopy(post["connections"])}
for n in post["nodes"]:
    if n["name"] == "Post Digest":
        continue
    if n["name"] == "Daily Trigger":
        n = {"parameters": {"httpMethod": "GET", "path": HOOK, "responseMode": "lastNode", "options": {}},
             "id": n["id"], "name": "Daily Trigger", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": n["position"], "webhookId": str(uuid.uuid4())}
    dev["nodes"].append(n)
dev["connections"].pop("Send Guard", None)
existing = [w for w in n8n("/api/v1/workflows?limit=250")["data"] if w["name"] == dev["name"]]
if existing:
    raise SystemExit("a DEV__dnc_morning_digest already exists (%s) - not creating a second" % existing[0]["id"])
wid = n8n("/api/v1/workflows", "POST", dev)["id"]
print("DEV copy %s created" % wid)
try:
    n8n("/api/v1/workflows/%s/activate" % wid, "POST", {})
    time.sleep(2)
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE.replace("/api/v1", "") + "/webhook/" + HOOK, timeout=600,
                                    context=ctx) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        out = {"HTTP": e.code, "body": e.read().decode()[:300]}
    print("ran in %.0fs" % (time.time() - t0))
    time.sleep(2)
    ex = n8n("/api/v1/executions?workflowId=%s&limit=1&includeData=true" % wid)["data"][0]
    rd = ex["data"]["resultData"]
    print("execution %s status=%s error=%s" % (ex["id"], ex["status"], json.dumps(rd.get("error"))[:300]))
    size = rd["runData"]["DT Size Agg"][0]["data"]["main"][0][0]["json"]
    print("DT Size Agg:", json.dumps({k: v for k, v in size.items() if k.startswith(("dt_", "__dt"))}))
    for n in ("DNC Active Rows", "DNC Removed Rows", "DT Domains Rows", "DT Claims Rows"):
        runs = rd["runData"][n]
        print("   %-18s runs=%d items=%d" % (n, len(runs), len(runs[0]["data"]["main"][0])))
    item = out[0] if isinstance(out, list) else out
    print("\n--- composed digest (NOT posted) ---\n" + (item.get("slack_text") if isinstance(item, dict) else str(item))[:3000])
finally:
    n8n("/api/v1/workflows/%s/deactivate" % wid, "POST", {})
    print("\nDEV copy %s deactivated (kept)" % wid)
