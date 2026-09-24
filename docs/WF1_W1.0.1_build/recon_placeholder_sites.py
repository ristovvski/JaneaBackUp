#!/usr/bin/env python3
"""READ ONLY. Every site that renders the blank-body placeholder, before changing the string.

Four surfaces to check:
  WF-1 `M7 Build`          -> render() feeds BOTH reply_text (alert) and reply_note (activity note)
  WF-2 `Body Reply Alert`  -> does its alert carry the reply text at all?
  WF-2 `Body Reply Activity` -> `if (n.reply.body) noteParts.push(...)` - a blank body currently
                                omits the line entirely, so the timeline says nothing
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

print("=== every occurrence of '[empty message]' estate-side ===")
for label, wf in (("WF-1", w1), ("WF-2", w2)):
    for n in wf["nodes"]:
        js = (n.get("parameters") or {}).get("jsCode") or ""
        if "empty message" in js:
            for i, l in enumerate(js.splitlines()):
                if "empty message" in l:
                    print("  %s / %-22s | %s" % (label, n["name"][:22], l.strip()[:100]))

print("\n=== WF-1 M7 Build: render() and its consumers ===")
mb = (N1["M7 Build"].get("parameters") or {}).get("jsCode") or ""
m = re.search(r"function render\(m\)[\s\S]{0,600}", mb)
if m:
    print(m.group(0)[:700])
for l in mb.splitlines():
    if re.search(r"reply_text|reply_note|__excerpt|Reply: ", l):
        print("   | %s" % l.strip()[:112])

print("\n=== WF-1: what the reply ACTIVITY note uses ===")
for nm in ("M7 Build", "M7 Reply Activity"):
    n = N1.get(nm)
    if not n:
        continue
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    for mm in re.findall(r"[^\"]{0,70}reply_note[^\"]{0,70}", blob):
        print("   %s | %s" % (nm, mm[:130]))

print("\n=== WF-2 Body Reply Alert: full code ===")
print((N2["Body Reply Alert"].get("parameters") or {}).get("jsCode") or "")

print("\n=== WF-2 Body Reply Activity: the note construction ===")
ba = (N2["Body Reply Activity"].get("parameters") or {}).get("jsCode") or ""
for l in ba.splitlines():
    if re.search(r"note|body|push", l, re.I):
        print("   | %s" % l.strip()[:112])
