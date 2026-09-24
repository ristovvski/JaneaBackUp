#!/usr/bin/env python3
"""Why does a 1-per-hour throttle produce a flood? Hypothesis: the staticData race defeats it.

`Verify Secret` already throttles correctly - it reads `__auth_warn_at` from staticData, and only
warns when an hour has passed. But n8n loads staticData per execution and persists it whole at the
end. Concurrent executions each read the SAME pre-warn snapshot, each conclude "an hour has passed",
and each warn. The counter then gets clobbered by whichever finishes last.

If true: adding more throttle logic changes nothing, and the fix is either the atomic store or
arming the secret so the warnings stop existing.

Test: count executions where __auth_warn === true per hour. More than one in any hour = defeated.
Then check whether those executions overlapped.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


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


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


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
print(f"executions to inspect: {len(ids)}")

warned, all_auth = [], []
for i, e in enumerate(ids, 1):
    if i % 150 == 0:
        print(f"   ...{i}/{len(ids)}", flush=True)
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        j = rd["Verify Secret"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    rec = {"id": e["id"], "a": ts(e.get("startedAt")), "b": ts(e.get("stoppedAt")),
           "mode": j.get("__auth_mode"), "warn": j.get("__auth_warn"),
           "supp": j.get("__auth_suppressed"),
           "posted": "Ops Warn Bad Secret" in rd}
    all_auth.append(rec)
    if rec["warn"] is True:
        warned.append(rec)

print(f"\nexecutions reaching Verify Secret : {len(all_auth)}")
print(f"   modes: {Counter(r['mode'] for r in all_auth)}")
print(f"   __auth_warn == true             : {len(warned)}")
print(f"   of those, actually POSTED       : {sum(1 for r in warned if r['posted'])}")

byhour = defaultdict(list)
for r in warned:
    if r["a"]:
        byhour[r["a"].strftime("%Y-%m-%d %HZ")].append(r)
print(f"\nwarnings per hour (a correct 1/hour throttle allows exactly 1):")
bad_hours = 0
for h in sorted(byhour)[-12:]:
    n = len(byhour[h])
    flag = "  <-- THROTTLE DEFEATED" if n > 1 else ""
    if n > 1:
        bad_hours += 1
    print(f"   {h}  {n}{flag}")
print(f"\nhours with more than one warning: {bad_hours}")

# did the multi-warn executions overlap each other?
print("\noverlap check on same-hour warn bursts")
for h in sorted(byhour):
    rows = sorted([r for r in byhour[h] if r["a"] and r["b"]], key=lambda r: r["a"])
    if len(rows) < 2:
        continue
    ovl = 0
    for i, r in enumerate(rows):
        for s in rows[i + 1:]:
            if s["a"] < r["b"]:
                ovl += 1
    print(f"   {h}: {len(rows)} warns, overlapping pairs: {ovl}"
          + ("   => race" if ovl else "   => sequential, throttle logic itself is wrong"))
