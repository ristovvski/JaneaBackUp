#!/usr/bin/env python3
"""READ ONLY. Confirm the accumulate-and-spread convention before patching `No Match Count`.

The question that decides item 1: does `Changelog Count` carry the WHOLE accumulated digest object
(in which case it is the replacement for the dead `$('I04 Status')`), or only its own fields (in
which case the digest needs a different context owner)?
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
DG = "qJKfR602wV9yfFrj"


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


wf = n8n("/api/v1/workflows/%s" % DG)
N = {n["name"]: n for n in wf["nodes"]}
for nm in ("Sched Agg", "Changelog Count", "Send Guard"):
    js = (N[nm].get("parameters") or {}).get("jsCode") or ""
    print("=" * 70)
    print("=== %s ===" % nm)
    print(js)

print("=" * 70)
print("=== every d.<field> Compose consumes (so we know what must survive) ===")
comp = (N["Compose"].get("parameters") or {}).get("jsCode") or ""
fields = sorted(set(re.findall(r"\bd\.([A-Za-z_][A-Za-z0-9_]*)", comp)))
print("  %d fields: %s" % (len(fields), ", ".join(fields)))

print("\n=== which of those does `No Match Count` itself produce? ===")
nmc = (N["No Match Count"].get("parameters") or {}).get("jsCode") or ""
own = sorted(set(re.findall(r"^\s*(?:__)?([a-z_][A-Za-z0-9_]*)\s*:", nmc, re.M)))
print("  own keys: %s" % own)
print("  -> everything else in Compose's list must arrive via the spread of `prev`.")

print("\n=== CONFIG keys the digest is configured with ===")
cfgp = (N["CONFIG"].get("parameters") or {})
vals = ((cfgp.get("assignments") or {}).get("assignments")
        or (cfgp.get("fields") or {}).get("values") or [])
for a in vals:
    nm = a.get("name")
    v = a.get("value")
    if isinstance(v, str) and len(v) > 60:
        v = v[:60] + "…"
    print("  %-34s = %s" % (nm, v))
