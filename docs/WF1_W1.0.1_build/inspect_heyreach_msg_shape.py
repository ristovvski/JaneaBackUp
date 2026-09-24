#!/usr/bin/env python3
"""READ ONLY. My empty-reply count is not trustworthy and this is why.

The first pass reported 342 reply events, 342 of them empty - 100%, which is not a finding, it is a
symptom. `extract_msg` looked for message/text/body/... and the HeyReach payload carries the thread
in **`recent_messages`**, which was not in my key list. Same class as reading Smartlead's
leads-statistics with the wrong keys and concluding "0 replies everywhere".

So: read the actual shape off the four Person-8768306e executions before counting anything.
"""
import json
import os
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


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
        raise


for eid in ("50115", "52059", "52060", "52061"):
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        b = (run["Webhook"][0]["data"]["main"][0][0].get("json") or {}).get("body") or {}
    except Exception as e:
        print("exec %s: no webhook data (%s)" % (eid, e))
        continue
    print("=" * 72)
    print("exec %s  event=%r  timestamp=%r" % (eid, b.get("event_type"), b.get("timestamp")))
    print("  top-level keys: %s" % sorted(b.keys()))
    rm = b.get("recent_messages")
    print("  recent_messages: type=%s len=%s"
          % (type(rm).__name__, len(rm) if isinstance(rm, (list, dict)) else "n/a"))
    if isinstance(rm, list):
        for i, m in enumerate(rm):
            if isinstance(m, dict):
                print("    [%d] keys=%s" % (i, sorted(m.keys())))
                print("        %s" % json.dumps(m, ensure_ascii=False)[:500])
            else:
                print("    [%d] %r" % (i, str(m)[:220]))
    elif rm is not None:
        print("    %s" % json.dumps(rm, ensure_ascii=False)[:500])
    print("  connection_message = %r" % str(b.get("connection_message"))[:200])
    print("  is_inmail=%r  conversation_id=%r  correlation_id=%r"
          % (b.get("is_inmail"), str(b.get("conversation_id"))[:44],
             str(b.get("correlation_id"))[:44]))
    lead = b.get("lead") or {}
    print("  lead: %r / %r  profile=%r"
          % (lead.get("full_name"), lead.get("position"), str(lead.get("profile_url"))[:60]))
