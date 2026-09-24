#!/usr/bin/env python3
"""READ ONLY, part three. Which field actually holds the LinkedIn URL on the three named orgs?

WF-1's `Org Create` writes `body[cfg.org_website_field]` as a TOP-LEVEL key on /api/v2. The native
org `website` field is `edit_flag: false`, so before writing a fix I want the evidence: read Brillio,
Pathomiq and Novo Nordisk and see which field carries the linkedin.com URL. That same field is what
the count in step 4 has to be run against.
"""
import json
import os
import re
import ssl
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"


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


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": "HTTP %s" % e.code}
    except Exception as e:
        return {"__err": str(e)[:120]}


w1 = n8n("/api/v1/workflows/%s" % WF1)
N1 = {n["name"]: n for n in w1["nodes"]}
raw = (N1["CONFIG"].get("parameters") or {}).get("jsonOutput")
try:
    cfg = json.loads(str(raw).lstrip("=").strip())
except Exception:
    cfg = {}
print("=== WF-1 CONFIG, top-level keys mentioning org/website/linkedin ===")
for k, v in sorted(cfg.items()):
    if re.search(r"org|website|linkedin|company", str(k), re.I):
        print("   %-28s = %r" % (k, v))

names = {f["key"]: f.get("name") for f in ((pd("/v1/organizationFields?limit=200") or {}).get("data") or [])}

print("\n=== the three named organizations ===")
for term in ("Brillio", "Pathomiq", "Novo Nordisk"):
    s = pd("/api/v2/organizations/search?fields=name&limit=3&term=" + urllib.parse.quote(term))
    items = ((s or {}).get("data") or {}).get("items") or []
    if not items:
        print("  %-14s NOT FOUND" % term)
        continue
    oid = (items[0].get("item") or {}).get("id")
    o = ((pd("/api/v2/organizations/%s" % oid) or {}).get("data") or {})
    print("\n  --- %s (id=%s) ---" % (o.get("name"), oid))
    for k in ("website", "address"):
        if o.get(k) is not None:
            print("     native %-12s = %r" % (k, o.get(k)))
    cf = o.get("custom_fields") or {}
    for k, v in cf.items():
        if v in (None, "", []):
            continue
        flag = "  <-- LINKEDIN URL" if re.search(r"linkedin\.com", str(v), re.I) else ""
        print("     cf %-42s (%-22s) = %r%s"
              % (k, str(names.get(k, "?"))[:22], str(v)[:60], flag))
