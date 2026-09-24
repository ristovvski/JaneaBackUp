#!/usr/bin/env python3
"""READ ONLY. Where does a company's LinkedIn URL end up, and where should it go?

Four things:
  1. WF-1's organization create/patch nodes and whatever builds their bodies
  2. WF-2's organization writer, if it has one
  3. the alert rows that print "Company website"
  4. Pipedrive's organization fields - is there a native/custom LinkedIn field to write instead?

Eleven days since the last session: re-read live rather than trusting the last known shape.
"""
import json
import os
import re
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
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


for tag, wid in (("WF-1", WF1), ("WF-2", WF2)):
    wf = n8n("/api/v1/workflows/%s" % wid)
    N = {n["name"]: n for n in wf["nodes"]}
    C = wf.get("connections") or {}
    print("=" * 76)
    print("%s  version=%s  nodes=%d  active=%s" % (tag, str(wf.get("versionId"))[:8],
                                                   len(wf["nodes"]), wf.get("active")))
    print("=" * 76)

    def par(name):
        return ["%s[%d]" % (s, bi) for s, spec in C.items()
                for bi, b in enumerate(spec.get("main") or [])
                for l in (b or []) if l and l.get("node") == name]

    print("-- organization write nodes --")
    for n in wf["nodes"]:
        p = n.get("parameters") or {}
        url = str(p.get("url") or "")
        if "organization" in url.lower() and str(p.get("method", "")).upper() in (
                "POST", "PUT", "PATCH"):
            print("   %-24s %-6s %s" % (n["name"][:24], p.get("method"), url[:70]))
            print("       parents=%s" % par(n["name"]))
    print("-- nodes whose code mentions company_url / website / organization body --")
    for n in wf["nodes"]:
        js = (n.get("parameters") or {}).get("jsCode") or ""
        if re.search(r"company_url|companyUrl|\bwebsite\b|organizations", js, re.I):
            hits = [l.strip() for l in js.splitlines()
                    if re.search(r"company_url|companyUrl|\bwebsite\b|linkedin", l, re.I)]
            if hits:
                print("   --- %s ---" % n["name"])
                for l in hits[:14]:
                    print("      | %s" % l[:112])

print("\n" + "=" * 76)
print("Pipedrive ORGANIZATION fields - looking for a LinkedIn field")
print("=" * 76)
of = (pd("/v1/organizationFields?limit=200") or {}).get("data") or []
print("  organization fields: %d" % len(of))
for f in of:
    nm = str(f.get("name") or "")
    if re.search(r"linkedin|website|url|domain", nm, re.I):
        print("   %-34s key=%-42s type=%s  edit_flag=%s"
              % (nm[:34], f.get("key"), f.get("field_type"), f.get("edit_flag")))
print("\n  (native org fields for reference)")
for f in of[:12]:
    print("   %-30s key=%-40s type=%s" % (str(f.get("name"))[:30], f.get("key"),
                                          f.get("field_type")))
