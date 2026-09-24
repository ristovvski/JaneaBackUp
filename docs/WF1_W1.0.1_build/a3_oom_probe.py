"""A3 — OOM diagnosis (background, non-blocking). Read-only against the n8n REST API.

Open question from wf2-oom-replay-burst.md: is the memory ceiling WF-2S (building a ~100-item
payload array in one Code node) or WF-2 (145 nodes x N executions fired concurrently by that
payload)? And is the n8n Cloud plan's memory limit visible/adjustable at all via the API?

The n8n public API does not expose process memory or infra limits directly, so this pass looks for
the closest available signal: exact timing/duration of the crashed executions (does WF-2S itself
finish quickly and it's WF-2's fan-out that dies, or does WF-2S never even finish building the
payload?), and the shape of the two documented crashes for a pattern.
"""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF2S = "6Y92ryBwYoy6z0Jx"
WF2 = "jp7rum9Z0YDJkQWv"
CRASH_EXECS_WF2S = [13391, 13551]           # the two documented WF-2S crash cycles


def n8n(path):
    try:
        r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
        with urllib.request.urlopen(r, timeout=180) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:300]}


print("=" * 96)
print("WF-2S CRASH EXECUTIONS - did the Code node (payload build) finish, or die mid-build?")
print("=" * 96)
for eid in CRASH_EXECS_WF2S:
    d = n8n(f"/api/v1/executions/{eid}?includeData=true")
    if d.get("__err"):
        print(f"  exec {eid}: {d}")
        continue
    print(f"\n  exec {eid}  status={d.get('status')}  "
          f"started={d.get('startedAt')} stopped={d.get('stoppedAt')}")
    rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
    print(f"  nodes with data: {list(rd.keys())}")
    err = (d.get("data") or {}).get("resultData", {}).get("error")
    if err:
        print(f"  top-level error: {json.dumps(err, ensure_ascii=False)[:500]}")
    bsp = rd.get("Build SENT Payload")
    if bsp:
        try:
            n_items = len(bsp[0]["data"]["main"][0])
            print(f"  Build SENT Payload completed: {n_items} items built")
        except Exception:
            print("  Build SENT Payload ran but shape unexpected")
    rep = rd.get("Replay Into WF-2")
    if rep:
        try:
            n_items = len(rep[0]["data"]["main"][0])
            errs = sum(1 for i in rep[0]["data"]["main"][0] if (i.get("json") or {}).get("error"))
            print(f"  Replay Into WF-2 completed: {n_items} items, {errs} carrying .error")
        except Exception as e:
            print(f"  Replay Into WF-2 present but did not complete cleanly: {e}")
    else:
        print("  Replay Into WF-2 has NO data at all -> WF-2S itself died before/during that node")

print("\n" + "=" * 96)
print("WF-2 EXECUTIONS DURING THOSE TWO WINDOWS - crashed there instead?")
print("=" * 96)
for lo, hi, label in (("2026-08-04T14:29:00Z", "2026-08-04T14:32:00Z", "outage-start burst"),
                      ("2026-08-05T06:59:00Z", "2026-08-05T07:05:00Z", "recovery-attempt burst")):
    ex = n8n(f"/api/v1/executions?workflowId={WF2}&limit=250")
    rows = [r for r in (ex.get("data") or []) if r.get("startedAt") and lo <= r["startedAt"] <= hi]
    print(f"\n  [{label}] {lo}..{hi}: {len(rows)} WF-2 executions")
    by_status = {}
    for r in rows:
        by_status[r.get("status")] = by_status.get(r.get("status"), 0) + 1
    print(f"    by status: {by_status}")
    for r in rows[:3]:
        d = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        err = (d.get("data") or {}).get("resultData", {}).get("error")
        print(f"    exec {r['id']} status={r.get('status')} "
              f"error={json.dumps(err, ensure_ascii=False)[:200] if err else None}")

print("\n" + "=" * 96)
print("ANY N8N INSTANCE/PLAN INFO EXPOSED VIA THE API?")
print("=" * 96)
for path in ("/api/v1/license", "/api/v1/source-control/status", "/api/v1/variables",
             "/api/v1/workflows?limit=1"):
    d = n8n(path)
    if isinstance(d, dict) and d.get("__err"):
        print(f"  {path} -> {d['__err']}")
    else:
        print(f"  {path} -> 200 ({str(d)[:150]})")
