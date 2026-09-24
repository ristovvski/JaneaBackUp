#!/usr/bin/env python3
"""READ ONLY. Before tombstoning Heath's row, establish that the removal path can do what is being
asked - specifically, whether `removed_reason` is caller-supplied or hardcoded.

The 7,450-row precedent used `POST /webhook/{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}` with
{row_ids, dry_run}. If that workflow stamps a fixed reason, then `false_reply_empty_body` cannot be
recorded through it, and that is a finding in its own right rather than something to work around
quietly.
"""
import json
import os
import re
import ssl
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
REG = "UOgKwlGsL28lX61O"


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        raise


cur, wfs = None, []
while True:
    q = {"limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
    wfs += d.get("data") or []
    cur = d.get("nextCursor")
    if not cur:
        break

print("=== workflows exposing a removal / retirement webhook ===")
targets = []
for w in wfs:
    full = n8n("/api/v1/workflows/%s" % w["id"])
    blob = json.dumps(full, ensure_ascii=False)
    if "retirement" in blob.lower() or "removed_reason" in blob:
        targets.append(full)
        print("  %s  %-7s %s" % (w["id"], "ACTIVE" if full.get("active") else "inact", w["name"]))

for full in targets:
    print("\n" + "=" * 74)
    print("=== %s (%s) nodes=%d active=%s ===" % (full["name"], full["id"], len(full["nodes"]),
                                                  full.get("active")))
    for n in full["nodes"]:
        p = n.get("parameters") or {}
        if n["type"].endswith("webhook"):
            print("  TRIGGER %s path=%r method=%r" % (n["name"], p.get("path"),
                                                      p.get("httpMethod")))
        if n["type"].endswith("dataTable"):
            print("  DATATABLE %-24s op=%-8s table=%s" % (
                n["name"][:24], p.get("operation"),
                ((p.get("dataTableId") or {}).get("value"))))
            cols = ((p.get("columns") or {}).get("value") or {})
            if cols:
                print("      columns: %s" % json.dumps(cols, ensure_ascii=False)[:400])
        js = p.get("jsCode") or ""
        if "removed_reason" in js or "dry_run" in js:
            print("  --- %s ---" % n["name"])
            for l in js.splitlines():
                if re.search(r"removed_reason|removed_at|dry_run|status|reason", l):
                    print("      | %s" % l.strip()[:116])

print("\n=== does anything read the registry table %s? (for locating Heath's row) ===" % REG)
for w in wfs:
    full = n8n("/api/v1/workflows/%s" % w["id"])
    for n in full["nodes"]:
        p = n.get("parameters") or {}
        if n["type"].endswith("dataTable") and ((p.get("dataTableId") or {}).get("value")) == REG \
                and p.get("operation") == "get":
            print("  %-34s / %-26s returnAll=%s" % (w["name"][:34], n["name"][:26],
                                                    p.get("returnAll")))
            break
