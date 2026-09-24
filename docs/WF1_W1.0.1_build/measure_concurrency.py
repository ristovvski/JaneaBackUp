#!/usr/bin/env python3
"""Measure ACTUAL concurrency per workflow, so the port list is evidence-led.

'Can it run in parallel' is a property of the trigger; 'does it' is a property of the traffic. An
overlap is any execution that starts before the previous one stops. Same-second starts are the
shape that lost Carla's key (three at 20:50:27).
READ ONLY. Writes concurrency_measure.json.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter, defaultdict

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = {"2jdjKM2NJr473GdA": "WF-1 HeyReach Receiver",
           "jp7rum9Z0YDJkQWv": "WF-2 Smartlead Receiver",
           "QO1zRhUfG7otk06N": "dnc_escalation_detector",
           "8qVXtI2ez5o6a9hc": "dnc_projections_sweep",
           "6Y92ryBwYoy6z0Jx": "WF-2S SENT Reconciler",
           "U8Bb7Pdq7S6nzYPa": "WF-2R REPLY Reconciler"}


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


out = {}
for wid, name in TARGETS.items():
    rows, cur, pages = [], None, 0
    while pages < 6:
        q = {"workflowId": wid, "limit": 250}
        if cur:
            q["cursor"] = cur
        d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
        ex = d.get("data") or []
        if not ex:
            break
        for r in ex:
            if r.get("startedAt"):
                rows.append({"id": r["id"], "start": r["startedAt"], "stop": r.get("stoppedAt")})
        cur = d.get("nextCursor")
        pages += 1
        if not cur:
            break
    rows.sort(key=lambda r: r["start"])
    same_sec = Counter(r["start"][:19] for r in rows)
    bursts = {k: v for k, v in same_sec.items() if v > 1}
    # true overlap: next starts before previous stops
    overlaps = 0
    for i in range(1, len(rows)):
        prev, curr = rows[i - 1], rows[i]
        if prev.get("stop") and curr["start"] < prev["stop"]:
            overlaps += 1
    out[name] = {"executions": len(rows), "window": (rows[0]["start"][:19] if rows else None,
                                                     rows[-1]["start"][:19] if rows else None),
                 "same_second_groups": len(bursts),
                 "executions_in_bursts": sum(bursts.values()),
                 "max_in_one_second": max(bursts.values()) if bursts else 1,
                 "true_overlaps": overlaps}
    print(f"{name:<34} execs={len(rows):>5}  same-second groups={len(bursts):>4}  "
          f"in-burst={sum(bursts.values()):>4}  max/sec={out[name]['max_in_one_second']}  "
          f"overlaps={overlaps}")

print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
for name, m in out.items():
    exposed = m["same_second_groups"] > 0 or m["true_overlaps"] > 0
    pct = (100 * m["executions_in_bursts"] // max(1, m["executions"]))
    print(f"  {name:<34} {'CONCURRENT — port required' if exposed else 'serial — no exposure'}"
          f"   ({pct}% of runs land in a shared second)")
json.dump(out, open(os.path.join(HERE, "concurrency_measure.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: concurrency_measure.json")
