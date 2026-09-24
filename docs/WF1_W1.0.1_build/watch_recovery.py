"""Watch the recovery cycles: per cycle, how many replayed, how many WF-2 accepted, how long it took.

Also confirms the new watchdog verdict (WF-2 active + shadow => no alarm) and reports the ledger
delta, i.e. how the seen-store grows as replays are finally accepted.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF2S = "6Y92ryBwYoy6z0Jx"
WF2 = "jp7rum9Z0YDJkQWv"
WAIT_MIN = int(os.environ.get("WATCH_MINUTES", "40"))
CYCLES = int(os.environ.get("WATCH_CYCLES", "2"))


def api(path):
    try:
        r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
        with urllib.request.urlopen(r, timeout=180) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}


def newest_ids(wid, n=60):
    d = api(f"/api/v1/executions?workflowId={wid}&limit={n}")
    return {r["id"]: r for r in (d.get("data") or []) if r.get("startedAt")}


seen_before = newest_ids(WF2S)
print(f"watching WF-2S for {CYCLES} new cycle(s), up to {WAIT_MIN} min")
print(f"  already retained: {len(seen_before)}")
deadline = time.time() + WAIT_MIN * 60
reported = 0
totals = {"batch": 0, "failed": 0, "marked": 0}

while time.time() < deadline and reported < CYCLES:
    time.sleep(30)
    now = newest_ids(WF2S)
    fresh = [r for i, r in now.items() if i not in seen_before and r.get("stoppedAt")]
    fresh.sort(key=lambda r: r["startedAt"])
    for r in fresh:
        seen_before[r["id"]] = r
        d = api(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
        started = r.get("startedAt")
        stopped = r.get("stoppedAt")
        dur = None
        try:
            dur = (datetime.fromisoformat(stopped.replace("Z", "+00:00"))
                   - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        except Exception:
            pass
        print("\n" + "=" * 92)
        print(f"CYCLE {r['id']}  {started}  status={r.get('status')}  duration={dur}s")
        print("=" * 92)
        if "Summary" not in rd:
            idle = "NoOp Idle" in rd
            print(f"  no Summary -> {'idle cycle (no new sends found)' if idle else 'check nodes'}")
            print(f"  nodes run: {list(rd.keys())[:14]}")
        else:
            try:
                j = rd["Summary"][0]["data"]["main"][0][0]["json"]
            except Exception:
                j = {}
            print(f"  Summary: {json.dumps(j, ensure_ascii=False)[:420]}")
            totals["batch"] += int(j.get("__batch") or 0)
            totals["failed"] += int(j.get("__failed") or 0)
            totals["marked"] += int(j.get("__marked") or 0)
            rep = rd.get("Replay Into WF-2")
            if rep:
                items = []
                try:
                    items = rep[0]["data"]["main"][0]
                except Exception:
                    items = []
                errs = [i for i in items if (i.get("json") or {}).get("error") is not None]
                print(f"  replays={len(items)} rejected={len(errs)} accepted={len(items) - len(errs)}")
                if errs:
                    m = ((errs[0].get("json") or {}).get("error") or {})
                    print(f"    first rejection: {str(m.get('message'))[:200]}")
            reported += 1
        # the watchdog's own verdict this cycle
        for nm in ("WF-2 Mode Eval",):
            if nm in rd:
                try:
                    w = rd[nm][0]["data"]["main"][0][0]["json"]
                    print(f"  watchdog: mode={w.get('__mode')!r} wf2_active={w.get('__wf2_active')} "
                          f"inactive={w.get('__wf2_inactive')} overdue={w.get('__mode_overdue')}")
                except Exception:
                    pass
        print(f"  alarm branch taken: {'Ops Warn Mode Overdue' in rd}  "
              f"(NoOp Mode OK: {'NoOp Mode OK' in rd})")
    if reported >= CYCLES:
        break

print("\n" + "=" * 92)
print("TOTALS OVER THE WATCHED CYCLES")
print("=" * 92)
print(f"  replayed={totals['batch']} rejected={totals['failed']} "
      f"marked_into_ledger={totals['marked']}")
wf2ex = api(f"/api/v1/executions?workflowId={WF2}&limit=250")
rows = [r for r in (wf2ex.get("data") or []) if r.get("startedAt")]
rows.sort(key=lambda r: r["startedAt"])
print(f"  WF-2 executions retained now: {len(rows)}"
      + (f"  ({rows[0]['startedAt']} .. {rows[-1]['startedAt']})" if rows else ""))
ok = sum(1 for r in rows if r.get("status") == "success")
print(f"  of those, success={ok} other={len(rows) - ok}")
