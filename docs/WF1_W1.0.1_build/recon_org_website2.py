#!/usr/bin/env python3
"""READ ONLY, part two.

WF-2 already carries a `W1.0.12 guard` in `Body Org Create` - so this may be WF-1-only. Confirm:
  a. WF-1 `Org Create` - its body is not in a Code node, so read the HTTP node's own parameters
  b. WF-2 `Body Org Create` in full - does the guard EXCLUDE website, or only additionally set
     the LinkedIn field?
  c. which field key `org_linkedin_lh` resolves to, in both CONFIGs
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
        raise


w1 = n8n("/api/v1/workflows/%s" % WF1)
w2 = n8n("/api/v1/workflows/%s" % WF2)
N1 = {n["name"]: n for n in w1["nodes"]}
N2 = {n["name"]: n for n in w2["nodes"]}

print("=== WF-1 Org Create: full parameters ===")
print(json.dumps(N1["Org Create"].get("parameters"), ensure_ascii=False, indent=1)[:2500])

print("\n=== WF-1: what feeds it (IF Org Found) and where company_url is read ===")
C1 = w1.get("connections") or {}
for nm in ("IF Org Found", "Org Search", "Normalize"):
    n = N1.get(nm)
    if not n:
        continue
    p = n.get("parameters") or {}
    if p.get("url"):
        print("  %-16s url=%s" % (nm, str(p["url"])[:110]))
    js = p.get("jsCode") or ""
    for l in js.splitlines():
        if re.search(r"company_url|company_name|org", l, re.I):
            print("  %-16s | %s" % (nm, l.strip()[:100]))

print("\n=== WF-1 CONFIG: org / linkedin field keys ===")
cfg1 = (N1["CONFIG"].get("parameters") or {}).get("jsonOutput")
try:
    blob = json.loads(str(cfg1).lstrip("=").strip())
except Exception:
    blob = {}
flds = blob.get("fields") or {}
for k, v in sorted(flds.items()):
    if re.search(r"org|linkedin|website|company", k, re.I):
        print("   fields.%-28s = %s" % (k, v))

print("\n=== WF-2 Body Org Create: full code ===")
print((N2["Body Org Create"].get("parameters") or {}).get("jsCode") or "")

print("\n=== WF-2 CONFIG: org / linkedin field keys ===")
cp = N2["CONFIG"].get("parameters") or {}
c2 = cp.get("jsonOutput")
if c2 is None:
    for a in ((cp.get("assignments") or {}).get("assignments") or []):
        if a.get("name") == "fields":
            c2 = a.get("value")
try:
    b2 = json.loads(str(c2).lstrip("=").strip()) if c2 else {}
except Exception:
    b2 = {}
f2 = b2.get("fields") or b2
for k, v in sorted((f2 or {}).items()):
    if re.search(r"org|linkedin|website|company", str(k), re.I):
        print("   fields.%-28s = %s" % (k, v))
