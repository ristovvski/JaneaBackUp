#!/usr/bin/env python3
"""READ ONLY. Groundwork for the blank-body gate, both receivers.

Three questions:
  1. WF-1: where does the M7 (reply) branch BEGIN? The gate has to sit upstream of every
     consequence - alert, labels, DNC, handover task, reply activity - not in front of one of them.
  2. WF-2: does the same shape exist? An alert / label / DNC row driven by an event whose
     correspondent body is blank. Smartlead's reply arrives as `reply_body`; is there any
     non-blank check today?
  3. Both alert bodies: do they quote the message at all? (WF-1's demonstrably does not, which is
     why an empty reply was indistinguishable from a real one for two days.)
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


def graph(wf):
    C = wf.get("connections") or {}

    def parents(name):
        return ["%s[%d]" % (s, bi) for s, spec in C.items()
                for bi, b in enumerate(spec.get("main") or [])
                for l in (b or []) if l and l.get("node") == name]

    def children(name):
        return ["%s[%d]" % (l["node"], bi)
                for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
                for l in (b or []) if l]
    return parents, children


print("=" * 78)
print("1. WF-1 - the M7 reply branch, from its entry down")
print("=" * 78)
wf1 = n8n("/api/v1/workflows/%s" % WF1)
N1 = {n["name"]: n for n in wf1["nodes"]}
par1, chi1 = graph(wf1)
m7 = sorted(n["name"] for n in wf1["nodes"] if n["name"].startswith("M7"))
print("  M7 nodes (%d): %s" % (len(m7), m7))
print("\n  entry points (M7 nodes whose parents are NOT M7):")
for nm in m7:
    ps = par1(nm)
    if not any(p.split("[")[0].startswith("M7") for p in ps):
        print("     %-26s parents=%s" % (nm[:26], ps))
        print("       children=%s" % chi1(nm))

print("\n  what routes events to M7 - the event switch/router:")
for n in wf1["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "message_reply_received" in blob or "every_message_reply" in blob:
        print("     %-26s type=%s" % (n["name"][:26], n["type"].split(".")[-1]))
        js = (n.get("parameters") or {}).get("jsCode")
        if js:
            keep = [l for l in js.splitlines()
                    if re.search(r"reply|message|event", l, re.I)][:16]
            for l in keep:
                print("        | %s" % l.strip()[:112])

print("\n  does WF-1 look at the message body ANYWHERE?")
for n in wf1["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    for tok in ("recent_messages", "is_reply", "connection_message"):
        if tok in blob:
            print("     %-26s mentions %r" % (n["name"][:26], tok))

print("\n" + "=" * 78)
print("2. WF-2 - same shape?")
print("=" * 78)
wf2 = n8n("/api/v1/workflows/%s" % WF2)
N2 = {n["name"]: n for n in wf2["nodes"]}
nz = (N2["Normalize"].get("parameters") or {}).get("jsCode") or ""
hits = [l.strip() for l in nz.splitlines() if re.search(r"reply_body|body|text", l, re.I)]
print("  Normalize lines touching the body (%d):" % len(hits))
for l in hits[:18]:
    print("     | %s" % l[:112])
blank = [n["name"] for n in wf2["nodes"]
         if re.search(r"reply_body[^\n]{0,40}(trim|length|!==\s*''|\?\?)",
                      json.dumps(n.get("parameters") or {}, ensure_ascii=False))]
print("\n  nodes that appear to test the body for emptiness: %s" % (blank or "NONE"))

print("\n" + "=" * 78)
print("3. alert bodies - do they quote the message?")
print("=" * 78)
for label, N in (("WF-1 M7 Critical Slack", N1.get("M7 Critical Slack")),
                 ("WF-2 Reply Alert", N2.get("Reply Alert")),
                 ("WF-2 Body Reply Alert", N2.get("Body Reply Alert"))):
    if not N:
        print("  %s: ABSENT" % label)
        continue
    p = N.get("parameters") or {}
    txt = p.get("text") or (p.get("jsCode") or "")
    print("\n  --- %s ---" % label)
    print("     %s" % str(txt)[:1100].replace("\n", "\n     "))
