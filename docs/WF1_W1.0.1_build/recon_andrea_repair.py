#!/usr/bin/env python3
"""Recon for the Person-7267ff83 repair. READ ONLY - plans nothing, writes nothing.

Her 'Interested' reply currently has: no alert, no forward, no lead, no label, no activity.
Person 69696 exists with 0 leads.

The repair must produce what WF-2 ITSELF would have written had the gate not eaten it - not a
hand-rolled approximation. So: read WF-2's own lead-creation and activity nodes for the exact body
shape, and read a sibling lead from the same campaign for the live title/field conventions.
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p):
    with urllib.request.urlopen(urllib.request.Request(
            BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=150, context=ctx) as x:
        return json.load(x)


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
NAMES = [n["name"] for n in wf["nodes"]]
print("WF-2 nodes that create/label leads or write activities:")
for n in wf["nodes"]:
    nm = n["name"]
    if any(k in nm for k in ("Create Lead", "Body Lead", "Label", "Activity", "Lead Create",
                             "Body Reply Activity", "Person Create")):
        print(f"  - {nm}  ({n['type'].split('.')[-1]})")
print()

for target in ("Body Create Lead", "Body Lead Create", "Create Lead", "Body Reply Activity",
               "Body Label", "Body Lead Labels"):
    n = next((x for x in wf["nodes"] if x["name"] == target), None)
    if not n:
        continue
    js = (n.get("parameters") or {}).get("jsCode") or ""
    print(f"=== {target} ===")
    if js:
        for i, l in enumerate(js.splitlines(), 1):
            print(f"{i:>3}| {l.rstrip()[:112]}")
    else:
        print(json.dumps(n.get("parameters"), indent=1)[:1200])
    print()

# the original webhook payload - the source of truth for the reply itself
det = n8n("/api/v1/executions/16265?includeData=true")
rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
raw = rd["Webhook"][0]["data"]["main"][0][0]["json"]
raw = raw.get("body", raw)
print("=== exec 16265 original webhook payload (the real reply) ===")
for k in ("campaign_id", "campaign_name", "sl_lead_email", "to_email", "to_name", "from_email",
          "sl_email_lead_id", "sl_email_lead_map_id", "message_id", "event_timestamp",
          "sequence_number", "subject"):
    print(f"   {k:<22} {repr(raw.get(k))[:70]}")
body = str(raw.get("reply_body") or raw.get("reply_message") or "")
print(f"   reply_body ({len(body)} chars): {body[:400]!r}")
print(f"   description: {str(raw.get('description'))[:200]!r}")

print("\n=== person 69696 ===")
p = pd("/api/v2/persons/69696")
d = (p or {}).get("data") or {}
print(f"   name={d.get('name')!r} org={(d.get('org_id') or {})}")
print(f"   emails={[e.get('value') for e in (d.get('emails') or [])]}")
print(f"   owner={(d.get('owner_id') or {})}")
cf = d.get("custom_fields") or {}
print(f"   custom_field keys: {len(cf)}")

print("\n=== sibling leads in the same campaign (conventions to copy) ===")
sib = pd(f"/v1/leads?limit=20&archived_status=all")
rows = (sib or {}).get("data") or []
cn = str(raw.get("campaign_name") or "")
match = [l for l in rows if cn and cn[:18].lower() in str(l.get("title") or "").lower()]
print(f"   leads read={len(rows)}  matching campaign name {cn[:26]!r}: {len(match)}")
for l in (match or rows)[:4]:
    print(f"   - {str(l.get('id'))[:8]} {str(l.get('title'))[:56]!r} "
          f"labels={len(l.get('label_ids') or [])} owner={l.get('owner_id')} "
          f"person={l.get('person_id')}")
