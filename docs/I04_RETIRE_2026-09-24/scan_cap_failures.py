#!/usr/bin/env python3
"""READ ONLY. Which data-table writes failed because the 50 MB cap was full, and when.

Error-status executions are not enough: most data-table nodes here run with onError continue*, so a
refused write shows up as a SUCCESS execution whose node output is an error item (or, for some ops,
an echo of its input). So every execution of every workflow that WRITES a data table is walked, node
by node, and each node's output items are parsed for an error whose message is the size-limit refusal.
Parsed field, not a substring of the whole blob (memory: no-substring-blob-checks).
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
env = {}
for line in open(os.path.join(os.path.dirname(HERE), ".env"), encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.strip().split("=", 1)
        env[k] = v.strip('"')
ctx = ssl.create_default_context(cafile=env.get("REQUESTS_CA_BUNDLE"))
B = env["N8N_BASE_URL"].rstrip("/")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-09-20T00:00"


def g(p):
    # small pages + backoff: full-data pages of 100 returned 502 - this instance has OOM'd before
    import time
    for attempt in range(5):
        try:
            r = urllib.request.Request(B + p, headers={"X-N8N-API-KEY": env["N8N_API_KEY"]})
            return json.load(urllib.request.urlopen(r, timeout=180, context=ctx))
        except urllib.error.HTTPError as e:
            if e.code not in (502, 503, 504) or attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))


wfs = g("/api/v1/workflows?limit=250")["data"]
writers = {}
for w in wfs:
    for n in w.get("nodes", []):
        if n["type"].endswith("dataTable") and n["parameters"].get("operation") in (
                "insert", "upsert", "update", "deleteRows"):
            writers.setdefault(w["id"], {"name": w["name"], "nodes": set()})["nodes"].add(n["name"])
print("workflows that write data tables: %d" % len(writers))


def msg_of(x):
    if isinstance(x, dict):
        e = x.get("error")
        if isinstance(e, dict):
            return str(e.get("message") or e.get("description") or "")
        if e is not None:
            return str(e)
    return ""


hits = defaultdict(list)
first_hit, last_ok = {}, {}
for wid, meta in writers.items():
    cur = None
    while True:
        d = g("/api/v1/executions?workflowId=%s&limit=10&includeData=true%s" % (wid, "&cursor=" + cur if cur else ""))
        stop = False
        for e in d["data"]:
            if e["startedAt"] < SINCE:
                stop = True
                break
            rd = (e.get("data") or {}).get("resultData") or {}
            top = msg_of({"error": rd.get("error")}) if rd.get("error") else ""
            found = "size limit" in top.lower()
            for node, runs in (rd.get("runData") or {}).items():
                for run in runs:
                    if "size limit" in msg_of({"error": run.get("error")}).lower():
                        found = True
                    for br in ((run.get("data") or {}).get("main") or []):
                        for it in (br or []):
                            if "size limit" in msg_of(it.get("json")).lower():
                                found = True
            if found:
                hits[meta["name"]].append((e["id"], e["startedAt"], e["status"]))
        cur = d.get("nextCursor")
        if stop or not cur:
            break
for name, hs in sorted(hits.items()):
    hs.sort(key=lambda h: h[1])
    print("%-40s %3d refused   first %s  last %s   statuses=%s" % (
        name[:40], len(hs), hs[0][1][:16], hs[-1][1][:16], sorted({h[2] for h in hs})))
json.dump({k: v for k, v in hits.items()}, open(os.path.join(HERE, "cap_failures.json"), "w"), indent=1)
if not hits:
    print("no size-limit refusals found since %s" % SINCE)
