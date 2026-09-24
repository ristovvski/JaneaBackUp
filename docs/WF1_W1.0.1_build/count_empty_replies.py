#!/usr/bin/env python3
"""READ ONLY. Re-count, correctly this time.

My first tally said "342 reply events, 342 empty" - 100%, which is a symptom, not a finding. Two
errors in it:

  * the message lives in **`recent_messages[]`** (`{creation_time, is_reply, message}`), which was
    not in my key list, so every event looked empty. Same class as reading Smartlead's
    leads-statistics with the wrong keys and confidently reporting zero replies.
  * `message_sent` (100 events) was counted as "reply-ish" because its name contains MESSAGE.

Correct definition used here:
  * a reply event is `message_reply_received` or `every_message_reply_received`
  * its content is the `recent_messages` entries with `is_reply: true` (the correspondent's side)
  * EMPTY = no such entry has a non-blank `message`

Also records whether each one ALERTED, because the alert count is what sizes the rule.
"""
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
REPLY_EVENTS = {"message_reply_received", "every_message_reply_received"}


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:120]}


def all_execs():
    out = {}
    for st in ("success", "error", "running", "waiting", "canceled"):
        cur = None
        while True:
            q = {"workflowId": WF1, "status": st, "limit": 250}
            if cur:
                q["cursor"] = cur
            d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q))
            for r in ((d or {}).get("data") or []):
                out[str(r["id"])] = r
            cur = (d or {}).get("nextCursor")
            if not cur:
                break
    return out


ex = all_execs()
print("executions in retention: %d" % len(ex))

rows, by_event, n = [], Counter(), 0
for eid, meta in sorted(ex.items(), key=lambda kv: str(kv[1].get("startedAt"))):
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    n += 1
    if n % 100 == 0:
        print("  %d/%d" % (n, len(ex)), flush=True)
    try:
        b = (run["Webhook"][0]["data"]["main"][0][0].get("json") or {}).get("body") or {}
    except Exception:
        continue
    ev = str(b.get("event_type") or "?")
    by_event[ev] += 1
    if ev not in REPLY_EVENTS:
        continue
    rm = b.get("recent_messages")
    rm = rm if isinstance(rm, list) else []
    theirs = [m for m in rm if isinstance(m, dict) and m.get("is_reply") is True]
    texts = [str(m.get("message") or "").strip() for m in theirs]
    empty = not any(texts)
    lead = b.get("lead") or {}
    alerted = "M7 Critical Slack" in run
    dnc = "M7 DNC Upsert Call" in run
    resp = "M7 Lead Patch" in run
    rows.append({"exec": eid, "at": str(meta.get("startedAt"))[:19], "event": ev,
                 "who": lead.get("full_name"), "profile": lead.get("profile_url"),
                 "campaign": (b.get("campaign") or {}).get("name")
                 if isinstance(b.get("campaign"), dict) else b.get("campaign"),
                 "their_msgs": len(theirs), "empty": empty,
                 "sample": (texts[0][:80] if texts and texts[0] else ""),
                 "alerted": alerted, "dnc_written": dnc, "lead_patched": resp})

print("\nevent types: %s" % json.dumps(by_event, ensure_ascii=False))
reps = [r for r in rows if r["event"] in REPLY_EVENTS]
emp = [r for r in reps if r["empty"]]
print("\nreply events            : %d" % len(reps))
for ev in sorted(REPLY_EVENTS):
    sub = [r for r in reps if r["event"] == ev]
    se = [r for r in sub if r["empty"]]
    print("  %-32s %4d   empty %4d  (%.0f%%)"
          % (ev, len(sub), len(se), 100.0 * len(se) / len(sub) if sub else 0))
print("\nEMPTY replies           : %d of %d (%.0f%%)"
      % (len(emp), len(reps), 100.0 * len(emp) / len(reps) if reps else 0))
print("  of the empty ones, how many had consequences:")
print("    alerted to Slack      : %d" % sum(1 for r in emp if r["alerted"]))
print("    DNC row written       : %d" % sum(1 for r in emp if r["dnc_written"]))
print("    lead patched (labels) : %d" % sum(1 for r in emp if r["lead_patched"]))
ne = [r for r in reps if not r["empty"]]
print("\n  non-empty replies       : %d   (alerted %d)"
      % (len(ne), sum(1 for r in ne if r["alerted"])))
print("\n  sample of REAL replies (proof the extractor works):")
for r in ne[:5]:
    print("    %-7s %-19s %-22s %r" % (r["exec"], r["at"], str(r["who"])[:22], r["sample"][:60]))
print("\n  sample of EMPTY ones:")
for r in emp[:8]:
    print("    %-7s %-19s %-22s their_msgs=%d alerted=%s dnc=%s"
          % (r["exec"], r["at"], str(r["who"])[:22], r["their_msgs"], r["alerted"],
             r["dnc_written"]))

with open(os.path.join(HERE, "empty_reply_census.json"), "w", encoding="utf-8") as f:
    json.dump({"executions": len(ex), "by_event": dict(by_event), "rows": rows},
              f, ensure_ascii=False, indent=1)
print("\n-> empty_reply_census.json")
