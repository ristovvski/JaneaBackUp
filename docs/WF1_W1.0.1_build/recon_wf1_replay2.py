#!/usr/bin/env python3
"""ITEM 4 recon, part two. READ ONLY.

Two specific questions the graph raised:
  A. `Create Lead` is gated ONLY by the claim row (`IF Lead Claimed[1]`) - there is no
     "does a lead already exist for this person+campaign?" lookup on that path. Confirm, and see
     what `Select Existing Lead` does on the claimed branch.
  B. `Person Create` is gated by `IF Member Verified` - a resolver. Would it adopt a person created
     30 s earlier by a failed attempt, or create a second one?
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


def parents(name):
    return ["%s[%d]" % (s, bi) for s, spec in C.items()
            for bi, b in enumerate(spec.get("main") or [])
            for l in (b or []) if l and l.get("node") == name]


def children(name):
    return ["%s[%d]" % (l["node"], bi)
            for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
            for l in (b or []) if l]


for nm in ("Lead Claim Key", "Select Existing Lead", "Create Lead", "Body Lead Create",
           "IF Member Verified", "Member Verify", "Person Get", "Person Search",
           "Resolve Person", "Person Resolve Ctx", "Dedupe", "Lead Claim Gate"):
    n = N.get(nm)
    if not n:
        print("--- %s: ABSENT ---" % nm)
        continue
    p = n.get("parameters") or {}
    print("=" * 74)
    print("--- %s (%s) ---" % (nm, n["type"].split(".")[-1]))
    print("   parents = %s" % parents(nm))
    print("   children= %s" % children(nm))
    if p.get("url"):
        print("   url=%s" % str(p["url"])[:170])
    cond = json.dumps(p.get("conditions") or {}, ensure_ascii=False)
    for m in re.findall(r'"leftValue":\s*"([^"]{0,180})"', cond):
        print("   IF: %s" % m)
    if p.get("jsCode"):
        print("   ---- code ----")
        print("   " + p["jsCode"][:2000].replace("\n", "\n   "))

print("=" * 74)
print("=== does ANY node look up an existing lead by person+campaign on the create path? ===")
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if re.search(r"/v1/leads\?|person_id=|leads\?limit", blob):
        print("  %-28s %s" % (n["name"][:28], str((n.get("parameters") or {}).get("url"))[:110]))
        print("      parents=%s" % parents(n["name"]))
