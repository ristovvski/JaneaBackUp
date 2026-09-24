#!/usr/bin/env python3
"""Ken's event carries campaign = None — a MANUAL HeyReach inbox conversation, not a campaign reply.
Quantify: how many recent team-channel alerts come from non-campaign conversations? That decides
whether the fix is 'check person known' (Ken was known) or 'do not alert on manual threads'."""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
TEAM = "C07LTD8UT70"


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


cur, pages, rows_seen = None, 0, 0
alerts = []
while pages < 8:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        rows_seen += 1
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "M7 Critical Slack" not in rd:
            continue

        def o(nm):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"]
            except Exception:
                return None

        cs = o("M7 Critical Slack") or {}
        if cs.get("ok") is not True or cs.get("channel") != TEAM:
            continue
        nz = o("Normalize") or {}
        camp = (nz.get("campaign") or {})
        cname = camp.get("name")
        gate = o("M7 Alert Gate") or {}
        alerts.append({"exec": r["id"], "at": r.get("startedAt"),
                       "campaign": cname, "campaign_id": camp.get("id"),
                       "lead": (nz.get("lead") or {}).get("full_name"),
                       "event": nz.get("event"),
                       "key": gate.get("__alert_key")})
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break

print(f"executions scanned: {rows_seen} over {pages} page(s)")
print(f"alerts DELIVERED to #lead-processing: {len(alerts)}\n")
nocamp = [a for a in alerts if not a["campaign"]]
withcamp = [a for a in alerts if a["campaign"]]
print(f"  from a CAMPAIGN conversation      : {len(withcamp)}")
print(f"  from a MANUAL (no campaign) thread: {len(nocamp)}"
      f"   <-- Ken's class")
print("\nmanual-thread alerts (most recent first):")
for a in sorted(nocamp, key=lambda x: str(x["at"]), reverse=True)[:12]:
    print(f"   {a['at']}  {str(a['lead'])[:26]:<26} event={str(a['event'])[:30]:<30} "
          f"key={str(a['key'])[-14:]!r}")
print("\ncampaign-thread alerts, by campaign:")
for k, v in Counter(str(a["campaign"])[:46] for a in withcamp).most_common(8):
    print(f"   {v:>3}  {k}")
print("\nalert-key suffix distribution (campaign part of the key):")
for k, v in Counter(str(a["key"]).rsplit("|", 1)[-1][:24] for a in alerts).most_common(8):
    print(f"   {v:>3}  {k!r}")
