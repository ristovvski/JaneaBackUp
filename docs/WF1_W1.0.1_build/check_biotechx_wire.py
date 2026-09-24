#!/usr/bin/env python3
"""READ ONLY. Wire-proof watch: has a BioTechX lead run through WF-1 since the org/LinkedIn deploy?

Deploy was versionId 658bea85 at epoch 1790073202. Anything BEFORE that ran on the old code and
proves nothing. Reports what ran, whether it carried a company_url, and which label the alert used.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"
DEPLOY_EPOCH = 1790073202


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {}


ex = {}
for st in ("success", "error", "running", "waiting"):
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
        {"workflowId": WF1, "status": st, "limit": 100}))
    for r in ((d or {}).get("data") or []):
        ex[str(r["id"])] = r
print("WF-1 executions in retention: %d" % len(ex))

found = []
for eid, meta in sorted(ex.items(), key=lambda kv: str(kv[1].get("startedAt")), reverse=True)[:80]:
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        b = (run["Webhook"][0]["data"]["main"][0][0].get("json") or {}).get("body") or {}
    except Exception:
        continue
    camp = b.get("campaign") or {}
    cname = str(camp.get("name") if isinstance(camp, dict) else camp or "")
    if "biotech" not in cname.lower():
        continue
    started = str(meta.get("startedAt"))
    after = ""
    try:
        import datetime
        t = datetime.datetime.strptime(started[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc).timestamp()
        after = "AFTER deploy" if t >= DEPLOY_EPOCH else "before deploy"
    except Exception:
        pass
    lead = b.get("lead") or {}
    row = {"exec": eid, "at": started[:19], "when": after, "event": b.get("event_type"),
           "campaign": cname[:54], "who": lead.get("full_name"),
           "company": lead.get("company_name"), "company_url": lead.get("company_url")}
    alert = ""
    if "M7 Build" in run:
        try:
            alert = str((run["M7 Build"][0]["data"]["main"][0][0]["json"] or {})
                        .get("alert_text") or "")
        except Exception:
            pass
    for l in alert.splitlines():
        if l.startswith("Company "):
            row["alert_line"] = l[:90]
    found.append(row)

if not found:
    print("\nNo BioTechX execution in retention yet - wire-proof still PENDING.")
    sys.exit(0)
print("\nBioTechX executions found: %d" % len(found))
for r in found:
    print("\n  exec %-7s %s  %s" % (r["exec"], r["at"], r["when"]))
    print("    event=%-32s who=%r" % (r["event"], r["who"]))
    print("    company=%r  company_url=%r" % (r["company"], r["company_url"]))
    if r.get("alert_line"):
        print("    alert -> %s" % r["alert_line"])
