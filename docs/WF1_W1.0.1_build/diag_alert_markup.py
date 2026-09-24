#!/usr/bin/env python3
"""Three questions about tonight's LinkedIn alerts. Read-only.

1. Confirm 2jdjKM2NJr473GdA is WF-1 and that it carries the unfurl + footer fixes. If it does, the
   "mystery poster" is WF-1 itself and the previews need a different explanation.
2. TIMING: were Cailong's and Jerod's alerts posted BEFORE the unfurl deploy? A preview on a
   pre-deploy post proves nothing about the fix.
3. The MARKUP BUG: dump the exact alert_text with codepoints around the LinkedIn URL, and trace
   where the trailing text comes from - the field value, or the builder.
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:110]}")
        return None


print("1. WHAT IS 2jdjKM2NJr473GdA?")
wf = n8n(f"/api/v1/workflows/{WF1}")
print(f"   name       : {wf.get('name')!r}")
print(f"   active     : {wf.get('active')}   nodes: {len(wf['nodes'])}")
print(f"   versionId  : {wf.get('versionId')}")
slack = [n for n in wf["nodes"] if n["type"].endswith("slack")]
for n in slack:
    oo = (n.get("parameters") or {}).get("otherOptions") or {}
    cred = ((n.get("credentials") or {}).get("slackApi") or {}).get("name")
    print(f"   [slack] {n['name']:<24} unfurl_links={oo.get('unfurl_links')!r} "
          f"footer={oo.get('includeLinkToWorkflow')!r} cred={cred}")

print("\n2. TIMING of the alerts vs the unfurl deploy")
ids = (n8n("/api/v1/executions", {"workflowId": WF1, "limit": 60}) or {}).get("data") or []
hits = []
for e in ids:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    if "M7 Critical Slack" not in rd:
        continue
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
        build = rd["M7 Build"][0]["data"]["main"][0][0]["json"]
        slk = rd["M7 Critical Slack"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    L = nm.get("lead") or {}
    hits.append({"exec": e["id"], "at": e.get("startedAt"), "who": L.get("full_name"),
                 "text": build.get("alert_text") or "", "ok": slk.get("ok"),
                 "ch": slk.get("channel"), "lead": L})
for h in sorted(hits, key=lambda r: str(r["at"]))[-6:]:
    print(f"   exec {h['exec']} {h['at']} {h['who']!r} ok={h['ok']} ch={h['ch']}")

print("\n3. MARKUP - codepoints around the LinkedIn URL")
for h in sorted(hits, key=lambda r: str(r["at"]))[-3:]:
    t = h["text"]
    print(f"\n   --- exec {h['exec']} {h['who']!r}")
    print(f"   raw alert_text ({len(t)} chars):")
    print(f"      {t!r}")
    i = t.find("linkedin.com")
    if i >= 0:
        seg = t[i:i + 80]
        print(f"   segment from 'linkedin.com': {seg!r}")
        print(f"   codepoints: {[hex(ord(c)) for c in seg[:60]]}")
    for bad, name in ((chr(0xFFFC), "U+FFFC OBJECT REPLACEMENT"),
                      (chr(0xFFFD), "U+FFFD REPLACEMENT"),
                      (chr(0x200B), "U+200B ZERO WIDTH SPACE")):
        if bad in t:
            j = t.find(bad)
            print(f"   *** {name} at index {j}: ...{t[max(0, j - 40):j + 40]!r}...")
    L = h["lead"]
    print(f"   source fields:")
    for k in ("profile_url", "company_name", "company_url", "full_name", "summary", "position"):
        v = L.get(k)
        if v is None:
            continue
        flag = ""
        for bad in (chr(0xFFFC), chr(0xFFFD), chr(0x200B)):
            if bad in str(v):
                flag = f"   <-- CONTAINS {hex(ord(bad))}"
        print(f"      {k:<14} {str(v)[:90]!r}{flag}")
