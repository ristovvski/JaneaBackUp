#!/usr/bin/env python3
"""READ ONLY. Where does WF-2's reply branch begin, and what does the body look like when it
arrives? The guard has to sit at the branch ENTRY, upstream of alert / label / DNC / activity, the
same as WF-1's.

Also: sample real reply bodies from retained executions, so the blank-test is calibrated against
what Smartlead actually sends rather than against an imagined shape. The two cases that matter are
an HTML body that strips to nothing, and a reply that is only a signature.
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
HERE = os.path.dirname(os.path.abspath(__file__))
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


def par(name):
    return ["%s[%d]" % (s, bi) for s, spec in C.items()
            for bi, b in enumerate(spec.get("main") or [])
            for l in (b or []) if l and l.get("node") == name]


def chi(name):
    return ["%s[%d]" % (l["node"], bi)
            for bi, b in enumerate(((C.get(name) or {}).get("main") or []))
            for l in (b or []) if l]


print("=== the reply branch, top down ===")
for nm in ("Normalize Parse", "Normalize", "IF Event Type", "Route Event", "Switch",
           "IF Reply", "Merge Reply Ctx", "LLM Classify", "Classify Body", "Classify Parse",
           "Alert Key", "First Reply Gate", "DNC Reply Gate"):
    if nm not in N:
        continue
    print("  %-22s type=%-12s" % (nm[:22], N[nm]["type"].split(".")[-1]))
    print("      parents = %s" % par(nm))
    print("      children= %s" % chi(nm))

print("\n=== anything that routes on event type ===")
for n in wf["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if re.search(r"REPLIED|EMAIL_REPLY", blob) and n["type"].split(".")[-1] in ("if", "switch",
                                                                               "filter"):
        print("  %-26s %s" % (n["name"][:26], n["type"].split(".")[-1]))
        for m in re.findall(r'"leftValue":\s*"([^"]{0,140})"', blob):
            print("      IF: %s" % m)
        for m in re.findall(r'"rightValue":\s*"([^"]{0,60})"', blob):
            print("      == %s" % m)

print("\n=== Normalize Parse: how `body` is built ===")
np = (N["Normalize Parse"].get("parameters") or {}).get("jsCode") or ""
for l in np.splitlines():
    if re.search(r"body|pick\(|reply_body|strip|html", l, re.I):
        print("   | %s" % l.strip()[:118])

print("\n=== sample REAL reply bodies from retained executions ===")
seen = 0
for st in ("success",):
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
        {"workflowId": WF2, "status": st, "limit": 60}))
    for r in ((d or {}).get("data") or []):
        f = n8n("/api/v1/executions/%s?includeData=true" % r["id"])
        run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
        try:
            nz = run["Normalize"][0]["data"]["main"][0][0]["json"]
        except Exception:
            continue
        body = nz.get("body") or (nz.get("reply") or {}).get("body")
        if body is None:
            for k in ("reply_body", "email_body", "text"):
                if k in nz:
                    body = nz[k]
                    break
        if not isinstance(body, str):
            continue
        txt = re.sub(r"(?s)<[^>]+>", " ", body)
        txt = re.sub(r"&nbsp;|&#160;", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        seen += 1
        print("  exec %-7s raw=%5d chars  stripped=%4d chars  %r"
              % (r["id"], len(body), len(txt), txt[:70]))
        if seen >= 12:
            break
    if seen >= 12:
        break
if not seen:
    print("  (no Normalize body captured in the sampled executions)")
