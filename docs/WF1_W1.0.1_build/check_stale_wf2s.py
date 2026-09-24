#!/usr/bin/env python3
"""Stale RUNNING execution on WF-2S, plus what the 112 unclassified WF-2 errors actually are.

A hung reconciler run can hold a cycle open, double-fire on the next tick, or sit on the burst that
caused the 429 storm - so identify it before touching the burst architecture. Read-only here:
killing it is a separate decision once I know what it is.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
NOW = datetime.now(timezone.utc)


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"   HTTP {e.code} on {p}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print("A. RUNNING / waiting executions across the estate")
for status in ("running", "waiting", "new"):
    for wid, tag in ((WF2S, "WF-2S"), (WF2, "WF-2"), ("U8Bb7Pdq7S6nzYPa", "WF-2R"),
                     ("2jdjKM2NJr473GdA", "WF-1")):
        p = n8n("/api/v1/executions", {"workflowId": wid, "limit": 50, "status": status})
        rows = (p or {}).get("data") or []
        for e in rows:
            t = ts(e.get("startedAt"))
            age = (NOW - t).total_seconds() / 60 if t else None
            print(f"   [{status:<7}] {tag:<6} exec {e['id']}  started={e.get('startedAt')}  "
                  f"age={age:.1f} min" if age is not None
                  else f"   [{status:<7}] {tag:<6} exec {e['id']}")

print("\nB. WF-2S recent runs (are cycles overlapping?)")
p = n8n("/api/v1/executions", {"workflowId": WF2S, "limit": 12})
prev = None
for e in sorted(((p or {}).get("data") or []), key=lambda r: str(r.get("startedAt"))):
    t = ts(e.get("startedAt"))
    st = ts(e.get("stoppedAt"))
    dur = (st - t).total_seconds() if (t and st) else None
    gap = (t - prev).total_seconds() / 60 if (prev and t) else None
    print(f"   exec {e['id']}  {e.get('startedAt')}  status={e.get('status')}  "
          f"dur={dur if dur is None else round(dur, 1)}s"
          + (f"  gap_from_prev={gap:.1f}min" if gap is not None else ""))
    prev = t

print("\nC. what ARE the 112 'errored' WF-2 executions with no lastNodeExecuted?")
p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": "error"})
sample, kinds = [], Counter()
for e in ((p or {}).get("data") or []):
    t = ts(e.get("startedAt"))
    if not t or t < datetime.fromisoformat("2026-08-11T14:30:00+00:00"):
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    if not det:
        continue
    rdata = ((det.get("data") or {}).get("resultData") or {})
    rd = rdata.get("runData") or {}
    if rdata.get("lastNodeExecuted"):
        continue
    kinds[tuple(sorted(rd.keys()))[:4]] += 1
    if len(sample) < 3:
        sample.append({"exec": e["id"], "at": e.get("startedAt"), "nodes": sorted(rd.keys())[:8],
                       "err": json.dumps(rdata.get("error") or {})[:200],
                       "mode": e.get("mode"), "retryOf": e.get("retryOf")})
print(f"   distinct node-signatures: {len(kinds)}")
for k, c in kinds.most_common(5):
    print(f"      [{c}x] first nodes: {list(k)}")
for s in sample:
    print(f"   sample exec {s['exec']} {s['at']} mode={s['mode']} nodes={s['nodes']}")
    print(f"      error={s['err']}")
