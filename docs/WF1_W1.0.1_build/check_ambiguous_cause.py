#!/usr/bin/env python3
"""exec 16278 keyed CRM to Andrea (correct) but classified 'ambiguous', not 'third_party', and
__reply_from came back as ANDREA rather than Marie-Anne. 'ambiguous' means a field was missing.

25 of 92 retained events classify ambiguous. If the missing field is systematically absent on a
whole arrival shape (replay / re-arrival / a provider variant), then third_party detection is off
for that entire class and the Ganga fix only half-works. Read the raw payload and find out which
field is absent, and whether it is absent by shape or by accident.
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
            timeout=150, context=ctx) as x:
        return json.load(x)


IDENT = ("sl_lead_email", "to_email", "from_email", "reply_email", "lead_email", "email",
         "sender_inbox", "to_name", "sl_email_lead_id", "campaign_id", "event_type")

for ex in (16278, 16265):
    det = n8n(f"/api/v1/executions/{ex}", {"includeData": "true"})
    rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
    print(f"=== exec {ex} ===")
    # the raw webhook payload as it entered
    src = None
    for nm in ("Webhook", "SL Webhook", "Smartlead Webhook", "Reply Webhook"):
        if nm in rd:
            src = nm
            break
    if not src:
        src = next((k for k in rd if "ebhook" in k or "rigger" in k), None)
    try:
        raw = rd[src][0]["data"]["main"][0][0]["json"]
        raw = raw.get("body", raw)
    except Exception:
        raw = {}
    print(f"  arrival node: {src}")
    for k in IDENT:
        v = raw.get(k)
        print(f"    {k:<18} {'ABSENT' if k not in raw else repr(v)[:60]}")
    extra = [k for k in raw if k not in IDENT]
    print(f"    other keys: {sorted(extra)[:18]}")
    try:
        nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        nz = {}
    print(f"  Normalize -> class={nz.get('__reply_class')!r} reply_from={nz.get('__reply_from')!r} "
          f"lead.email={(nz.get('lead') or {}).get('email')!r} "
          f"reply_category={nz.get('reply_category')!r}")
    err = ((det.get("data") or {}).get("resultData") or {}).get("error") or {}
    if err:
        print(f"  ERROR: node={err.get('node', {}).get('name')} "
              f"msg={str(err.get('message'))[:90]}")
    print()

# how common is the missing field across all retained EMAIL_REPLY arrivals?
print("=== how many retained replies lack the field, and does it track a shape? ===")
ids = (n8n("/api/v1/executions", {"workflowId": WF2, "limit": 120}) or {}).get("data") or []
tally, shapes = {}, {}
for e in ids[:120]:
    try:
        d = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        r = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
        nz = r["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    if str(nz.get("event_type") or "").upper().find("REPLY") < 0:
        continue
    c = nz.get("__reply_class") or "(pre-fix build)"
    tally[c] = tally.get(c, 0) + 1
    if c == "ambiguous":
        miss = tuple(k for k in ("sl_lead_email", "to_email") if not nz.get(k))
        shapes[miss] = shapes.get(miss, 0) + 1
for k, v in sorted(tally.items(), key=lambda t: -t[1]):
    print(f"   {k:<18} {v}")
print("   ambiguous, by which identity field is missing:")
for k, v in sorted(shapes.items(), key=lambda t: -t[1]):
    print(f"      missing={k or '(neither - other cause)'}  {v}")
