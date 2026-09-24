#!/usr/bin/env python3
"""Item 7 - how many PAST replies hit the to_email vs sl_lead_email mis-mapping? Read-only.

Every EMAIL_REPLY where `to_email != sl_lead_email` is a threaded reply from someone who is not the
campaign lead. On each of those, WF-2 identified the WRONG human, so the REAL lead is missing its
`3. Responded` label and its reply activity - the same repair shape as the London backfill.

Also prints WF-2's Normalize reply-branch mapping, which is where the defect lives.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


print("A. WF-2 Normalize - the reply-branch identity mapping (where the defect lives)")
wf = n8n(f"/api/v1/workflows/{WF2}")
nz = next((n for n in wf["nodes"] if n["name"] == "Normalize"), None)
js = ((nz or {}).get("parameters") or {}).get("jsCode") or ""
for i, line in enumerate(js.splitlines(), 1):
    if any(t in line for t in ("to_email", "sl_lead_email", "email:", "lead:", "reply")):
        print(f"   {i:3}| {line.strip()[:118]}")

print("\nB. SWEEP - every retained EMAIL_REPLY, comparing to_email vs sl_lead_email")
ids, cursor = [], None
while True:
    q = {"workflowId": WF2, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor:
        break
print(f"   executions retained: {len(ids)}")

replies, mismatched, kinds = 0, [], Counter()
for i, e in enumerate(ids, 1):
    if i % 150 == 0:
        print(f"   ...{i}/{len(ids)}", flush=True)
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
    if str(body.get("event_type")) != "EMAIL_REPLY":
        continue
    replies += 1
    to_e = str(body.get("to_email") or "").strip().lower()
    lead_e = str(body.get("sl_lead_email") or "").strip().lower()
    if not to_e or not lead_e:
        kinds["missing one of the two fields"] += 1
        continue
    if to_e == lead_e:
        kinds["normal - sender IS the lead"] += 1
        continue
    kinds["THIRD-PARTY reply"] += 1
    alert = None
    try:
        alert = rd["Reply Alert"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    mismatched.append({
        "exec": e["id"], "at": e.get("startedAt"),
        "campaign": body.get("campaign_id"), "campaign_name": body.get("campaign_name"),
        "real_lead": lead_e, "replied_from": to_e,
        "alerted": (alert or {}).get("ok") is True,
        "channel": (alert or {}).get("channel"),
        "forwarded": "SL Forward Email" in rd,
    })

print(f"\n   EMAIL_REPLY events examined: {replies}")
for k, v in kinds.most_common():
    print(f"      {k:<32} {v}")

print(f"\nC. THE AFFECTED SET: {len(mismatched)} third-party replies")
for m in sorted(mismatched, key=lambda r: str(r["at"])):
    print(f"   {m['at']}  exec {m['exec']}")
    print(f"      real lead : {m['real_lead']}")
    print(f"      replied by: {m['replied_from']}")
    print(f"      alerted={m['alerted']} ch={m['channel']} forwarded={m['forwarded']}  "
          f"campaign {m['campaign']} {str(m['campaign_name'])[:40]!r}")

print("\nD. REPAIR SCOPE - do the REAL leads have their Responded label?")
seen_leads = {}
for m in mismatched:
    em = m["real_lead"]
    if em in seen_leads:
        continue
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(em)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or [] if pid else []
    has_resp = [l for l in leads if RESPONDED in (l.get("label_ids") or [])]
    seen_leads[em] = (pid, len(leads), len(has_resp))
    print(f"   {em:<40} person={pid} leads={len(leads)} with_Responded={len(has_resp)}"
          f"{'   <-- MISSING' if leads and not has_resp else ''}")
print(f"\n   distinct real leads needing repair: "
      f"{sum(1 for v in seen_leads.values() if v[1] and not v[2])} of {len(seen_leads)}")
