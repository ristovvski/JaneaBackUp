#!/usr/bin/env python3
"""ITEM 4 recon. READ ONLY.

The auditor's conclusion - "a processing failure before the claim + a HeyReach retry = duplicate
person and lead" - is the whole reason not to move the ack. Before proposing a two-phase claim I
want to know whether it is true, because WF-1's normal path already RESOLVES before it creates:
if a full replay adopts the person and the campaign lead that attempt 1 created, the duplicate
hazard is much narrower than stated and the fix is smaller.

So: walk the create path and answer three questions from the graph, not from belief.
  1. Is `Person Create` gated by a resolver that would find a person created 30 s earlier?
  2. Is `Create Lead` gated by a lead lookup that matches on something attempt 1 would have set?
  3. Which of those gates can MISS - i.e. where does a replay actually duplicate?
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
WF1 = "2jdjKM2NJr473GdA"


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


wf = n8n("/api/v1/workflows/%s" % WF1)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print("WF-1 version=%s nodes=%d active=%s" % (wf.get("versionId"), len(wf["nodes"]),
                                              wf.get("active")))


def parents(name):
    return ["%s[%d]" % (s, bi) for s, spec in C.items()
            for bi, b in enumerate(spec.get("main") or [])
            for l in (b or []) if l and l.get("node") == name]


def children(name):
    return ["%s[%d]" % (l["node"], bi)
            for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
            for l in (b or []) if l]


print("\n=== every WRITE to Pipedrive, and what gates it ===")
for n in wf["nodes"]:
    p = n.get("parameters") or {}
    if n["type"].endswith("httpRequest") and str(p.get("method", "")).upper() in (
            "POST", "PUT", "PATCH", "DELETE"):
        print("  %-26s %-6s %s" % (n["name"][:26], p.get("method"), str(p.get("url"))[:66]))
        print("      parents=%s" % parents(n["name"]))

print("\n=== the claims-table nodes and their position in the order ===")
for n in wf["nodes"]:
    if n["type"].endswith("dataTable"):
        p = n.get("parameters") or {}
        print("  %-26s op=%-8s parents=%s" % (n["name"][:26], p.get("operation"),
                                              parents(n["name"])))

print("\n=== resolver / existence gates: what do they MATCH ON? ===")
for nm in ("Person Search", "Person Resolve", "Person Pick", "Person Id Final", "IF Person Found",
           "Lead Select", "IF Lead Exists", "Lead Claim Gate", "IF Lead Claimed",
           "DT Lead Claim Get", "DT Lead Claim Set", "DT Claim Seen"):
    n = N.get(nm)
    if not n:
        continue
    p = n.get("parameters") or {}
    print("\n  --- %s (%s) ---" % (nm, n["type"].split(".")[-1]))
    print("      parents=%s" % parents(nm))
    print("      children=%s" % children(nm))
    if p.get("url"):
        print("      url=%s" % str(p["url"])[:150])
    if p.get("jsCode"):
        js = p["jsCode"]
        keep = [l for l in js.splitlines()
                if re.search(r"campaign|match|exact|title|email|linkedin|member|public_id|claim",
                             l, re.I)]
        for l in keep[:14]:
            print("      | %s" % l.strip()[:118])
    cond = json.dumps(p.get("conditions") or {}, ensure_ascii=False)
    if len(cond) > 2:
        for m in re.findall(r'"leftValue":\s*"([^"]{0,150})"', cond):
            print("      IF: %s" % m)
