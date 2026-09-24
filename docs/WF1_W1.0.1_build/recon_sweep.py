#!/usr/bin/env python3
"""READ ONLY. Item 3 recon: how does `dnc_projections_sweep` get started, what does MODE="dev"
actually do, and what does it report? Nothing is fired here."""
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
cands = [w for w in listing if "projection" in w["name"].lower() or "sweep" in w["name"].lower()]
print("=== candidates ===")
for w in cands:
    print("  %s  %s  %s" % (w["id"], "ACTIVE" if w.get("active") else "inact ", w["name"]))

t = next((w for w in cands if w["name"] == "dnc_projections_sweep"), cands[0] if cands else None)
if not t:
    raise SystemExit("no sweep workflow")
wf = n8n("/api/v1/workflows/%s" % t["id"])
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print("\n=== %s  id=%s  active=%s  nodes=%d  version=%s ===" % (
    wf["name"], wf["id"], wf.get("active"), len(wf["nodes"]), wf.get("versionId")))

print("\n=== TRIGGERS (how it can be started) ===")
for n in wf["nodes"]:
    if "rigger" in n["type"] or "webhook" in n["type"].lower():
        p = n.get("parameters") or {}
        print("  %-26s %-40s %s" % (n["name"][:26], n["type"],
                                    json.dumps({k: v for k, v in p.items()
                                                if k in ("path", "httpMethod", "rule")},
                                               ensure_ascii=False)[:160]))

print("\n=== CONFIG ===")
for nm, n in N.items():
    p = n.get("parameters") or {}
    vals = ((p.get("assignments") or {}).get("assignments")
            or (p.get("fields") or {}).get("values") or [])
    if vals and ("CONFIG" in nm or "Config" in nm):
        print("  --- %s ---" % nm)
        for a in vals:
            v = a.get("value")
            v = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            print("    %-32s = %s" % (a.get("name"), v[:100]))

print("\n=== nodes that WRITE (must stay dark in dev) ===")
for n in wf["nodes"]:
    p = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    meth = (n.get("parameters") or {}).get("method")
    if n["type"].endswith("httpRequest") and str(meth).upper() in ("POST", "PUT", "PATCH", "DELETE"):
        url = str((n.get("parameters") or {}).get("url"))[:78]
        print("  %-30s %-6s %s" % (n["name"][:30], meth, url))
    elif n["type"].endswith("slack"):
        print("  %-30s SLACK" % n["name"][:30])

print("\n=== where MODE / FIRE_ are read (the gates) ===")
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if re.search(r"MODE|FIRE_PIPEDRIVE|FIRE_SMARTLEAD|dry", blob):
        print("  %-30s %-14s" % (n["name"][:30], n["type"].split(".")[-1]))

print("\n=== the reporting node's code (what number comes out of a dev run) ===")
for nm in ("Report", "Summary", "Compose", "Post Summary", "Build Report"):
    if nm in N and (N[nm].get("parameters") or {}).get("jsCode"):
        print("  --- %s ---" % nm)
        print("  " + N[nm]["parameters"]["jsCode"][:1800].replace("\n", "\n  "))
        break
else:
    print("  (no obvious report node; node list follows)")
    for n in wf["nodes"]:
        print("    %-30s %s" % (n["name"][:30], n["type"].split(".")[-1]))
