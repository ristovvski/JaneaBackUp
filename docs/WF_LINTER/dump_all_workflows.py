#!/usr/bin/env python3
"""Dump every workflow, full objects, for the linters to read. READ ONLY against n8n.

Paged to exhaustion on purpose - a capped list read is the estate's most-repeated measurement bug,
and a linter that silently sees 30 of 41 workflows reports a clean estate.
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_all_workflows.json")


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


cur, listing = None, []
while True:
    q = {"limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
    listing += d.get("data") or []
    cur = d.get("nextCursor")
    if not cur:
        break

full = [n8n("/api/v1/workflows/%s" % w["id"]) for w in listing]
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(full, f, ensure_ascii=False)
active = sum(1 for w in full if w.get("active"))
print("workflows dumped: %d  (%d active, %d inactive)" % (len(full), active, len(full) - active))
print("nodes total      : %d" % sum(len(w.get("nodes") or []) for w in full))
print("-> %s" % OUT)
sys.exit(0)
