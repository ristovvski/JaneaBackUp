#!/usr/bin/env python3
"""Wait for the flip-gate lead's first send and report the EXACT address it came from - that is
the address Nik must reply to, and it is not knowable in advance because the campaign rotates
sending inboxes. Also reports whether a reply has landed yet. READ-ONLY."""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
CID = 3686187
LEAD = "4306240392"
EMAIL = "pii-c61c7d08@example.invalid"
HERE = os.path.dirname(os.path.abspath(__file__))
DEADLINE = time.time() + 60 * 88


def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    try:
        r = urllib.request.Request(
            f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
            headers={"User-Agent": "janea-r4-watch/1.0"})
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code}
    except Exception as e:
        return {"__err": str(e)[:120]}


print(f"watching lead {LEAD} ({EMAIL}) in campaign {CID} for its first send, from "
      f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z", flush=True)
sent = None
while time.time() < DEADLINE:
    h = sl(f"/campaigns/{CID}/leads/{LEAD}/message-history")
    hist = (h or {}).get("history") or []
    sents = [x for x in hist if str(x.get("type", "")).upper() == "SENT"]
    reps = [x for x in hist if str(x.get("type", "")).upper() == "REPLY"]
    if sents and not sent:
        sent = sents[0]
        print("\n" + "=" * 80, flush=True)
        print("SEND FIRED", flush=True)
        print("=" * 80, flush=True)
        print(f"  time    : {sent.get('time')}", flush=True)
        print(f"  FROM    : {sent.get('from')}   <-- Nik replies to THIS address", flush=True)
        print(f"  to      : {sent.get('to')}", flush=True)
        print(f"  subject : {sent.get('subject')!r}", flush=True)
        print(f"  msg id  : {sent.get('message_id')}", flush=True)
    if reps:
        print(f"\nREPLY DETECTED at {reps[-1].get('time')} - the flip gate has an organic "
              f"end-to-end event", flush=True)
        break
    if sent:
        # send confirmed; keep watching a little for the reply, then hand off
        time.sleep(120)
    else:
        time.sleep(60)

out = {"lead_id": LEAD, "email": EMAIL, "campaign_id": CID,
       "sent": sent, "checked_at": datetime.now(timezone.utc).isoformat()}
with open(os.path.join(HERE, "wf1-release-evidence", "r4_send_watch.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
if not sent:
    print("\nno send yet inside the watch window. The campaign schedule is 07:00-17:00 "
          "America/Los_Angeles with 22 min between emails - if the window has closed, the send "
          "lands at the next open window.", flush=True)
print("wrote wf1-release-evidence/r4_send_watch.json", flush=True)
