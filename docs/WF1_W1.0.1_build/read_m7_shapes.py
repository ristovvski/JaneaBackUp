#!/usr/bin/env python3
"""Philip's lead fb215d20 is HUMAN-owned (title 'Phil Cootey', no campaign field, two hand-written
activities by owner 25733113). The repair must be exactly what M7 would have done and nothing more:
union-add the responded label, write the reply activity. No title rewrite, no campaign backfill,
no owner change - those are conventions for leads WE create.

Read WF-1's own label ids and M7's label/activity shapes."""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
blob = json.dumps(N["CONFIG"]["parameters"], ensure_ascii=False)
raw = blob.encode().decode("unicode_escape")
i = raw.lower().find("labels")
print("=== WF-1 CONFIG, labels region ===")
print(raw[max(0, i - 60):i + 420])
print("\n=== activity type / owner region ===")
for k in ("owner_id", "activity", "reply_activity", "channel"):
    j = raw.find(k)
    if j >= 0:
        print(f"  {k}: {raw[max(0,j-4):j+120]}")

print("\n=== M7 Labels Compute ===")
js = (N.get("M7 Labels Compute") or {}).get("parameters", {}).get("jsCode", "")
for i2, l in enumerate(js.splitlines(), 1):
    print(f"{i2:>3}| {l.rstrip()[:114]}")

print("\n=== M7 Reply Activity (params) ===")
p = (N.get("M7 Reply Activity") or {}).get("parameters", {})
print(json.dumps(p, ensure_ascii=False, indent=1)[:1800])
