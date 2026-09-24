#!/usr/bin/env python3
"""Which WF-2R node builds the replay envelope, and does it have the lead email in hand?

Smartlead's leads-statistics rows key on `to` / `lead_id` - `to` IS the campaign lead's address.
If WF-2R already reads that, restoring sl_lead_email is a one-field addition, not new plumbing.
"""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

with urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/v1/workflows/U8Bb7Pdq7S6nzYPa",
        headers={"X-N8N-API-KEY": KEY}), timeout=150, context=ctx) as x:
    wf = json.load(x)

print(f"WF-2R  versionId={wf.get('versionId')}  active={wf.get('active')}  "
      f"nodes={len(wf['nodes'])}\n")
for n in wf["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    body = json.dumps(n.get("parameters") or {})
    if "to_email" in js or "event_type" in js or "__reconciled" in body:
        print(f"--- {n['name']}  ({n['type'].split('.')[-1]}) ---")
        if js:
            for i, line in enumerate(js.splitlines(), 1):
                if re.search(r"to_email|sl_lead_email|event_type|__reconciled|lead_id|"
                             r"\bto\b|campaign_id", line):
                    print(f"  {i:>3}| {line.rstrip()[:118]}")
        else:
            print(f"  params: {body[:600]}")
        print()
print("node names:", [n["name"] for n in wf["nodes"]])
