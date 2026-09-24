#!/usr/bin/env python3
"""The replay envelope has no sl_lead_email -> every WF-2R-recovered reply classifies 'ambiguous'
-> the Ganga gate suppresses its team alert.

Two of my own fixes interacting: P0-1b/WF-2R recovers a crashed reply, and the Ganga gate then
silences it. "Recovered" would stop meaning "delivered". Quantify before believing it:
  * how many retained EMAIL_REPLY arrivals are reconciled replays vs live webhooks
  * does sl_lead_email track that shape exactly, or is it also missing on live arrivals
  * in the replay envelope, what does to_email actually mean - the lead, or whoever replied
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


ids = (n8n("/api/v1/executions", {"workflowId": WF2, "limit": 200}) or {}).get("data") or []
print(f"scanning {len(ids)} retained WF-2 executions\n")
rows = []
for e in ids:
    try:
        d = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
        raw = rd["Webhook"][0]["data"]["main"][0][0]["json"]
        raw = raw.get("body", raw)
    except Exception:
        continue
    if str(raw.get("event_type") or "").upper() != "EMAIL_REPLY":
        continue
    try:
        nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        nz = {}
    rows.append({
        "id": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
        "replay": bool(raw.get("__reconciled") or raw.get("__reconciled_by")),
        "by": raw.get("__reconciled_by"),
        "has_sl": bool(raw.get("sl_lead_email")),
        "sl": raw.get("sl_lead_email"), "to": raw.get("to_email"),
        "same": (str(raw.get("sl_lead_email") or "").lower()
                 == str(raw.get("to_email") or "").lower()) if raw.get("sl_lead_email") else None,
        "cls": nz.get("__reply_class"),
    })

live = [r for r in rows if not r["replay"]]
rep = [r for r in rows if r["replay"]]
print(f"EMAIL_REPLY arrivals retained : {len(rows)}")
print(f"   live webhook               : {len(live)}   sl_lead_email present: "
      f"{sum(1 for r in live if r['has_sl'])}/{len(live)}")
print(f"   WF-2R / reconciled replay   : {len(rep)}   sl_lead_email present: "
      f"{sum(1 for r in rep if r['has_sl'])}/{len(rep)}")
print(f"   reconciled_by values        : "
      f"{sorted({str(r['by']) for r in rep})}\n")

print("does sl_lead_email absence track the replay shape exactly?")
print(f"   live arrivals MISSING sl_lead_email   : {sum(1 for r in live if not r['has_sl'])}")
print(f"   replays MISSING sl_lead_email         : {sum(1 for r in rep if not r['has_sl'])}")

print("\nclassification of the arrivals that ran the NEW Normalize:")
newb = [r for r in rows if r["cls"]]
t = {}
for r in newb:
    k = (r["cls"], "replay" if r["replay"] else "live")
    t[k] = t.get(k, 0) + 1
for k, v in sorted(t.items(), key=lambda x: -x[1]):
    print(f"   {k[0]:<12} {k[1]:<7} {v}")
if not newb:
    print("   (none yet - the new build has seen too little traffic to judge from classes alone)")

print("\non LIVE arrivals, how often is to_email the lead vs a different human?")
withsl = [r for r in live if r["has_sl"]]
print(f"   to_email == sl_lead_email : {sum(1 for r in withsl if r['same'])}/{len(withsl)}")
for r in [r for r in withsl if not r["same"]][:6]:
    print(f"      exec {r['id']}  lead={r['sl']}  replied={r['to']}")

print("\nreplays: is to_email the LEAD? (compare against the same event's live arrival if retained)")
for r in rep[:8]:
    print(f"   exec {r['id']}  {r['at']}  status={r['status']}  to_email={r['to']}  cls={r['cls']}")
