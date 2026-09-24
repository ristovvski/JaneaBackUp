#!/usr/bin/env python3
"""READ ONLY. Two facts needed to place the WF-2 guard, read rather than assumed:
  a. which `Switch Event` output is REPLIED, and what it feeds
  b. the exact key the reply body lands on in Normalize's emitted object
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
WF2 = "jp7rum9Z0YDJkQWv"


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
        return {}


wf = n8n("/api/v1/workflows/%s" % WF2)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}

print("=== Switch Event: rule order and wiring ===")
sw = N["Switch Event"]
for i, r in enumerate(((sw.get("parameters") or {}).get("rules") or {}).get("values") or []):
    conds = ((r.get("conditions") or {}).get("conditions") or [])
    rv = [c.get("rightValue") for c in conds]
    print("  output[%d] outputKey=%r rightValue=%s" % (i, r.get("outputKey"), rv))
for bi, b in enumerate(((C.get("Switch Event") or {}).get("main") or [])):
    print("  wired[%d] -> %s" % (bi, [l["node"] for l in (b or []) if l]))

print("\n=== Normalize: the emitted keys around the body ===")
nz = (N["Normalize"].get("parameters") or {}).get("jsCode") or ""
tail = nz[-2500:]
for l in tail.splitlines():
    if re.search(r"body|reply|msg|text", l, re.I):
        print("   | %s" % l.strip()[:118])

print("\n=== Normalize Parse: the object it returns ===")
np_ = (N["Normalize Parse"].get("parameters") or {}).get("jsCode") or ""
m = re.search(r"return\s*\[?\{[\s\S]{0,2500}$", np_)
if m:
    for l in m.group(0).splitlines():
        if re.search(r"body|reply|text|:", l):
            print("   | %s" % l.strip()[:118])

print("\n=== who consumes the body downstream (classifier, alert, activity) ===")
for nm in ("Classify Body", "Body Reply Activity", "Body Reply Alert"):
    js = (N.get(nm, {}).get("parameters") or {}).get("jsCode") or ""
    for l in js.splitlines():
        if re.search(r"\bbody\b|reply_body|reply_text", l):
            print("  %-22s | %s" % (nm[:22], l.strip()[:100]))
