#!/usr/bin/env python3
"""Activate WF-2R. A 200 from /activate is not proof - this re-reads the workflow afterwards and
also states, from the live CONFIG, exactly why the already-backfilled replies cannot be replayed."""
import json, os, ssl, sys, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2R = "U8Bb7Pdq7S6nzYPa"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
        raise


before = n8n(f"/api/v1/workflows/{WF2R}")
cfg = json.loads(next(n for n in before["nodes"]
                      if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
floor = cfg["ignore_replies_before"]
print(f"before: active={before.get('active')} versionId={before.get('versionId')}")
print(f"reply floor: {floor}")

# the ten backfilled replies, newest first - state the guarantee rather than hoping for it
NEWEST_BACKFILLED = "2026-08-05T06:08:38+00:00"     # pii-280f963f@example.invalid
f = datetime.fromisoformat(floor.replace("Z", "+00:00"))
n = datetime.fromisoformat(NEWEST_BACKFILLED)
if n >= f:
    print(f"REFUSING TO ACTIVATE: the newest backfilled reply ({NEWEST_BACKFILLED}) is at or "
          f"after the floor ({floor}) - activation could replay work already done by hand, "
          f"double-forwarding pii-6f8f48e5@example.invalid to Rune.")
    sys.exit(2)
print(f"guarantee: newest backfilled reply {NEWEST_BACKFILLED} is "
      f"{(f - n).total_seconds() / 3600:.1f}h BEFORE the floor -> structurally unreplayable")

n8n(f"/api/v1/workflows/{WF2R}/activate", "POST", {})
after = n8n(f"/api/v1/workflows/{WF2R}")
print(f"\nafter: active={after.get('active')} versionId={after.get('versionId')}")
if after.get("active") is not True:
    print("ACTIVATION DID NOT TAKE - live read says active is not true")
    sys.exit(1)
cfg2 = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
for k in ("ignore_replies_before", "max_per_run", "max_campaigns_per_cycle", "lookback_minutes"):
    if cfg2.get(k) != cfg.get(k):
        print(f"CONFIG DRIFT on activate: {k} {cfg.get(k)!r} -> {cfg2.get(k)!r}")
        sys.exit(1)
print("verified live: active=True, CONFIG unchanged by the activate call")
print(f"first cycle expected within 15 min of {datetime.now(timezone.utc).strftime('%H:%M:%S')}Z")
