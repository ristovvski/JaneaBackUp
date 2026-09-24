#!/usr/bin/env python3
"""Dump the CURRENT M7 Alert Gate and M7 Labels Compute verbatim - the gate was revised on
2026-08-31 (STABLE KEY) since I last edited it, so the port must be built against what is live now,
not what I remember. READ ONLY."""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


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


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-1 versionId {wf.get('versionId')}  nodes={len(wf['nodes'])}")
for nm in ("M7 Alert Gate", "M7 Labels Compute"):
    js = N[nm]["parameters"]["jsCode"]
    with open(os.path.join(HERE, f"_live_{nm.replace(' ', '_')}.js"), "w",
              encoding="utf-8") as f:
        f.write(js)
    print(f"\n{'=' * 74}\n{nm}  ({len(js.splitlines())} lines)\n{'=' * 74}")
    print(js)
C = wf.get("connections") or {}
print("\n=== wiring around the gate ===")
for k in ("M7 Build", "M7 Alert Gate", "M7 IF Should Alert", "M7 Critical Slack",
          "M7 IF Patch", "M7 Person Patch", "M7 Alert Suppressed",
          "AR Post? M7 Critical Slack", "AR Ctx M7 Critical Slack", "AR Decide"):
    if k in C:
        print(f"  {k:<28} -> {json.dumps(C[k].get('main'), ensure_ascii=False)[:150]}")
print("\n=== node positions ===")
for k in ("M7 Build", "M7 Alert Gate", "M7 IF Should Alert", "M7 Critical Slack",
          "M7 Labels Compute", "M7 IF Patch"):
    if k in N:
        print(f"  {k:<24} {N[k].get('position')}")
