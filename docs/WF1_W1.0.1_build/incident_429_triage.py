#!/usr/bin/env python3
"""429-STORM TRIAGE. Crashed / recoverable / lost - and 'lost' must be ZERO if P0-1b works.

This is P0-1b's first real trial. Its whole claim: a crashed execution leaves its dedupe key
UNCLAIMED, so the event stays replayable. So the decisive number is not how many crashed - it is
how many crashed events hold a claim they should not.

Three questions, answered from data:
  1. WHAT failed, and with what error (open the actual failed executions, do not infer from alerts)
  2. Is every crashed event RECOVERABLE - key absent from wf2_seen AND inside WF-2S/WF-2R's reach
  3. Is the backlog draining or growing (cap vs arrival rate)
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S, WF2R = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx", "U8Bb7Pdq7S6nzYPa"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   n8n read failed: {str(e)[:110]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print("=" * 96)
print("1. FAILED EXECUTIONS - what actually errored")
failed = []
for status in ("error", "crashed"):
    p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": status})
    failed += (p or {}).get("data") or []
print(f"   failed WF-2 executions returned by the API: {len(failed)}")

detail, nodes_failed, errors, keys = [], Counter(), Counter(), []
for e in failed:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    if not det:
        continue
    rdata = ((det.get("data") or {}).get("resultData") or {})
    rd = rdata.get("runData") or {}
    last = rdata.get("lastNodeExecuted")
    err = rdata.get("error") or {}
    msg = str(err.get("message") or "")[:150]
    nodes_failed[last] += 1
    errors[msg[:80]] += 1
    ded = None
    try:
        ded = rd["Dedupe"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    nm = None
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    detail.append({"exec": e["id"], "at": e.get("startedAt"), "node": last, "err": msg,
                   "event": (nm or {}).get("event"),
                   "key": (ded or {}).get("__dedupe_key"),
                   "dup": (ded or {}).get("__duplicate")})
    if (ded or {}).get("__dedupe_key"):
        keys.append(ded["__dedupe_key"])

print(f"\n   failing node:")
for n, c in nodes_failed.most_common():
    print(f"      {str(n):<34} {c}")
print(f"   error messages:")
for m, c in errors.most_common(6):
    print(f"      [{c}x] {m}")
if detail:
    d0 = sorted(detail, key=lambda x: str(x["at"]))[0]
    dl = sorted(detail, key=lambda x: str(x["at"]))[-1]
    print(f"   window: {d0['at']} .. {dl['at']}")
print(f"   events by type: {Counter(d['event'] for d in detail)}")

print("\n" + "=" * 96)
print("2. RECOVERABILITY - P0-1b's first real trial")
wf = n8n(f"/api/v1/workflows/{WF2}")
seen = ((wf.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
claimed = [k for k in keys if k in seen]
unclaimed = [k for k in keys if k not in seen]
print(f"   crashed executions with a dedupe key : {len(keys)}")
print(f"   of those, key UNCLAIMED (replayable) : {len(unclaimed)}")
print(f"   of those, key CLAIMED  (LOST)        : {len(claimed)}")
for k in claimed:
    print(f"      *** LOST: {k}")

now = datetime.now(timezone.utc)
outside = []
for d in detail:
    t = ts(d["at"])
    if t and (now - t) > timedelta(hours=48):
        outside.append(d["exec"])
print(f"   crashed events older than 48h (outside reconciler reach): {len(outside)}")

print("\n" + "=" * 96)
print("3. RECONCILER STATE / BACKLOG")
for wid, tag in ((WF2S, "WF-2S"), (WF2R, "WF-2R")):
    w = n8n(f"/api/v1/workflows/{wid}")
    sd = (w.get("staticData") or {}).get("global") or {}
    cfg = next((n for n in w["nodes"] if n["name"] == "CONFIG"), None)
    blob = json.dumps((cfg or {}).get("parameters") or {}, ensure_ascii=False)
    caps = {}
    for field in ("max_per_run", "page_limit", "max_campaigns_per_cycle",
                  "max_pages_per_campaign", "lookback_minutes"):
        i = blob.find(field)
        if i >= 0:
            caps[field] = blob[i + len(field):i + len(field) + 18].strip('\\": ,')
    store_keys = {k: (len(v) if isinstance(v, dict) else v) for k, v in sd.items()
                  if isinstance(v, (dict, int, str))}
    print(f"   {tag}: active={w.get('active')} caps={caps}")
    print(f"      staticData sizes: {json.dumps(store_keys)[:200]}")
    ex = n8n("/api/v1/executions", {"workflowId": wid, "limit": 6})
    for e in ((ex or {}).get("data") or [])[:4]:
        print(f"      run {e['id']} {e.get('startedAt')} status={e.get('status')}")
