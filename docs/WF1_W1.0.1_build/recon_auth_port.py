#!/usr/bin/env python3
"""READ ONLY. Item 2 shape recon: copy the ported three rather than invent a fourth convention.

Needs: the exact dataTable node parameters (columns, matching, dataTableId mode), where
`Verify Secret` sits in the graph, and who consumes `__auth_warn` / `__auth_suppressed`.
"""
import json
import os
import re
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


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


wf = n8n("/api/v1/workflows/%s" % WF2)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}


def parents(name):
    out = []
    for src, spec in C.items():
        for bi, branch in enumerate(spec.get("main") or []):
            for link in (branch or []):
                if link and link.get("node") == name:
                    out.append("%s[%d]" % (src, bi))
    return out


def children(name):
    return ["%s[%d]" % (l["node"], bi)
            for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
            for l in (b or []) if l]


print("=== the auth path, as wired ===")
for nm in ("Webhook", "Respond to Webhook", "Verify Secret", "CONFIG"):
    if nm in N:
        print("  %-22s parents=%s" % (nm, parents(nm)))
        print("  %-22s children=%s" % ("", children(nm)))

print("\n=== who consumes __auth_warn / __auth_ok / __auth_suppressed ===")
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    hits = sorted(set(re.findall(r"__auth_[a-z_]+", blob)))
    if hits:
        print("  %-26s %-12s %s" % (n["name"][:26], n["type"].split(".")[-1], hits))
        print("      parents=%s" % parents(n["name"]))

print("\n=== EXACT parameters of the ported dataTable nodes (the convention to copy) ===")
for nm in ("DT Alert Get", "DT Alert Claim", "DT Dedupe Get", "DT Claim Dedupe"):
    if nm not in N:
        print("  %s: ABSENT" % nm)
        continue
    n = N[nm]
    print("\n  --- %s (typeVersion=%s onError=%s) ---" % (nm, n.get("typeVersion"),
                                                          n.get("onError")))
    print("  " + json.dumps(n.get("parameters"), ensure_ascii=False, indent=1).replace("\n", "\n  "))
    print("  alwaysOutputData=%s  retryOnFail=%s" % (n.get("alwaysOutputData"),
                                                     n.get("retryOnFail")))

print("\n=== how a ported code node reads a dataTable result (the positive-shape rule) ===")
for nm in ("Alert Gate", "First Reply Gate", "Dedupe Gate", "Bounce Gate"):
    if nm in N and (N[nm].get("parameters") or {}).get("jsCode"):
        js = N[nm]["parameters"]["jsCode"]
        m = re.search(r"[\s\S]{0,600}?(isRow|claimed_at)[\s\S]{0,400}", js)
        if m:
            print("\n  --- %s ---" % nm)
            print("  " + m.group(0).replace("\n", "\n  "))
            break

print("\n=== CONFIG: the auth-notice knobs ===")
cfgp = N["CONFIG"].get("parameters") or {}
vals = ((cfgp.get("assignments") or {}).get("assignments")
        or (cfgp.get("fields") or {}).get("values") or [])
for a in vals:
    nm = str(a.get("name") or "")
    if "secret" in nm or "warn" in nm or "channel" in nm or "ops" in nm:
        print("  %-40s = %s" % (nm, str(a.get("value"))[:70]))
