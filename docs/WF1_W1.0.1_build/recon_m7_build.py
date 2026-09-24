#!/usr/bin/env python3
"""READ ONLY. `M7 Build` already renders '[empty message]' - so WF-1 KNOWS the body is blank and
alerts anyway. Read the whole node, find where it sits, and see what alert_text actually contains.

Also: WF-2's Normalize has no line touching the reply body, so find where WF-2 does read it.
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


wf1 = n8n("/api/v1/workflows/%s" % WF1)
N1 = {n["name"]: n for n in wf1["nodes"]}
C1 = wf1.get("connections") or {}


def par(C, name):
    return ["%s[%d]" % (s, bi) for s, spec in C.items()
            for bi, b in enumerate(spec.get("main") or [])
            for l in (b or []) if l and l.get("node") == name]


def chi(C, name):
    return ["%s[%d]" % (l["node"], bi)
            for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
            for l in (b or []) if l]


print("=== M7 Build position ===")
print("  parents = %s" % par(C1, "M7 Build"))
print("  children= %s" % chi(C1, "M7 Build"))
print("\n=== Switch routing (which output is the reply branch) ===")
sw = N1.get("Switch")
print(json.dumps((sw.get("parameters") or {}), ensure_ascii=False, indent=1)[:1800])
print("\n  Switch children by output:")
for bi, b in enumerate(((C1.get("Switch") or {}).get("main") or [])):
    print("     [%d] -> %s" % (bi, [l["node"] for l in (b or []) if l]))

print("\n=== M7 Build full code ===")
print((N1["M7 Build"].get("parameters") or {}).get("jsCode") or "")

print("\n=== Normalize: how msgs is built ===")
nz = (N1["Normalize"].get("parameters") or {}).get("jsCode") or ""
for l in nz.splitlines():
    if re.search(r"msgs|recent_messages|connection_message|is_reply", l):
        print("   | %s" % l.strip()[:120])

print("\n\n=== WF-2: where is the reply body read? ===")
wf2 = n8n("/api/v1/workflows/%s" % WF2)
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if re.search(r"reply_body|email_body|\breply\b.{0,12}text", blob, re.I):
        js = (n.get("parameters") or {}).get("jsCode") or ""
        hits = [l.strip() for l in js.splitlines()
                if re.search(r"reply_body|email_body|reply_text", l, re.I)][:8]
        print("  --- %s (%s) ---" % (n["name"], n["type"].split(".")[-1]))
        for h in hits:
            print("     | %s" % h[:118])
        if not hits:
            m = re.findall(r"[^\"]{0,60}(?:reply_body|email_body)[^\"]{0,60}", blob)
            for x in m[:3]:
                print("     ~ %s" % x[:118])
