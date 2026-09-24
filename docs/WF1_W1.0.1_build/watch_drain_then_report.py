#!/usr/bin/env python3
"""Watch the 32 released events drain. Reports when it is safe to bounce WF-2S.

Done means BOTH halves, per the two-store rule that this incident just taught:
  * WF-2S re-detected and replayed it   -> stats_id back in __sent_seen_v2
  * WF-2 actually processed it          -> its dedupe key present in wf2_seen
A stats_id back in __sent_seen_v2 ALONE proves only that it was sent again - which is precisely the
false signal that made these look recoverable in the first place.

Also watches for fresh 429 crashes: if the spaced burst still trips the rate limit, that is a RED
and the bounce waits.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
START = datetime.now(timezone.utc)
DEADLINE = START + timedelta(minutes=int(os.environ.get("WATCH_MIN", "70")))
LOG = os.path.join(HERE, "wf1-release-evidence", "drain_watch.log")
RELEASED = json.load(open(os.path.join(HERE, "wf1-release-evidence", "released_ids.json"),
                          encoding="utf-8")) if os.path.exists(
    os.path.join(HERE, "wf1-release-evidence", "released_ids.json")) else None


def say(m):
    line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        say(f"  read failed (NOT an empty result): {str(e)[:100]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


say(f"=== drain watch from {START.isoformat()} ===")
say("done = stats_id back in __sent_seen_v2 AND its dedupe key claimed in wf2_seen")
base_seen = None
while datetime.now(timezone.utc) < DEADLINE:
    ws = n8n(f"/api/v1/workflows/{WF2S}")
    w2 = n8n(f"/api/v1/workflows/{WF2}")
    if not ws or not w2:
        time.sleep(60)
        continue
    sseen = ((ws.get("staticData") or {}).get("global") or {}).get("__sent_seen_v2") or {}
    wseen = ((w2.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
    if base_seen is None:
        base_seen = len(sseen)
    # fresh crashes since the spacing fix?
    ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60, "status": "error"})
    fresh = [e for e in ((ex or {}).get("data") or [])
             if (ts(e.get("startedAt")) or START) >= START]
    say(f"  __sent_seen_v2={len(sseen)} (started {base_seen}, target ~195)  "
        f"wf2_seen={len(wseen)}  new errors since watch start={len(fresh)}")
    if fresh:
        say(f"  *** {len(fresh)} NEW errored executions since the spacing fix - investigate "
            f"before bouncing")
        for e in fresh[:5]:
            say(f"      exec {e['id']} {e.get('startedAt')}")
    if len(sseen) >= 195:
        say("\nDRAIN COMPLETE - __sent_seen_v2 back at pre-release size")
        say("safe to bounce WF-2S for stale exec 14183")
        sys.exit(0)
    time.sleep(120)

say("\nwatch window ended without reaching the target - do NOT bounce yet; report instead")
sys.exit(1)
