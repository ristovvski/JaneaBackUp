#!/usr/bin/env python3
"""READ ONLY. Items 1 and 2 recon.

1) dnc_morning_digest: what does the digest actually report today, what feeds `No Match Count`, and
   what does `Compose` expect from it? The auditor deliberately refused to guess the replacement for
   the dead `$('I04 Status')` reference; this reads the contract instead of inferring it.
2) WF-2 `Verify Secret`: the staticData auth-notice state, and the shape of the THREE already-ported
   stores so the fourth matches them rather than inventing a fourth convention.
"""
import json
import os
import ssl
import urllib.parse
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


def all_workflows():
    cur, out = None, []
    while True:
        q = {"limit": 250}
        if cur:
            q["cursor"] = cur
        d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
        out += d.get("data") or []
        cur = d.get("nextCursor")
        if not cur:
            return out


wfs = all_workflows()
dg = [w for w in wfs if "digest" in w["name"].lower()]
print("=== digest-ish workflows ===")
for w in dg:
    print("  %s  %s  %s" % (w["id"], "ACTIVE" if w.get("active") else "inact ", w["name"]))

target = next((w for w in dg if w["name"] == "dnc_morning_digest"), dg[0] if dg else None)
if not target:
    raise SystemExit("no digest workflow found")

wf = n8n("/api/v1/workflows/%s" % target["id"])
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print("\n=== %s  id=%s  nodes=%d  version=%s ===" % (wf["name"], wf["id"], len(wf["nodes"]),
                                                     wf.get("versionId")))

# who feeds No Match Count, and what does No Match Count feed
def parents(name):
    out = []
    for src, spec in C.items():
        for branch in (spec.get("main") or []):
            for link in (branch or []):
                if link and link.get("node") == name:
                    out.append(src)
    return out


for nm in ("No Match Count", "Compose", "I04 Status"):
    print("\n  --- %s ---" % nm)
    if nm not in N:
        print("     ABSENT from the workflow")
        continue
    n = N[nm]
    print("     type=%s  parents=%s" % (n["type"].split(".")[-1], parents(nm)))
    kids = [l["node"] for b in ((C.get(nm) or {}).get("main") or []) for l in (b or []) if l]
    print("     children=%s" % kids)

print("\n=== full node list, in graph order-ish ===")
for n in wf["nodes"]:
    print("  %-28s %-14s parents=%s" % (n["name"][:28], n["type"].split(".")[-1], parents(n["name"])))

for nm in ("No Match Count", "Compose"):
    if nm in N and (N[nm].get("parameters") or {}).get("jsCode"):
        print("\n=== %s jsCode ===" % nm)
        print(N[nm]["parameters"]["jsCode"])

print("\n=== every $('...') reference in this workflow, per node ===")
import re
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    refs = sorted(set(re.findall(r"\$\(\\?['\"]([^'\"\\]+)\\?['\"]\)", blob)))
    if refs:
        miss = [r for r in refs if r not in N]
        print("  %-28s %s%s" % (n["name"][:28], refs, "   MISSING=%s" % miss if miss else ""))

# ---------------------------------------------------------------- item 2
print("\n\n================ ITEM 2: WF-2 Verify Secret + the ported three ================")
wf2 = n8n("/api/v1/workflows/%s" % WF2)
N2 = {n["name"]: n for n in wf2["nodes"]}
print("WF-2 version=%s nodes=%d" % (wf2.get("versionId"), len(wf2["nodes"])))
vs = N2.get("Verify Secret")
if vs:
    print("\n=== Verify Secret jsCode ===")
    print((vs.get("parameters") or {}).get("jsCode") or "(no jsCode)")

print("\n=== every remaining getWorkflowStaticData user in WF-2 (the port target list) ===")
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "getWorkflowStaticData" in blob:
        keys = sorted(set(re.findall(r"sd\.(__[A-Za-z0-9_]+)", blob)))
        print("  %-30s keys=%s" % (n["name"][:30], keys))

print("\n=== the THREE already-ported stores: how they read/write the claims table ===")
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "euyostwJYfJefItC" in blob:
        print("  %-30s type=%-16s op=%s" % (
            n["name"][:30], n["type"].split(".")[-1],
            (n.get("parameters") or {}).get("operation")))
