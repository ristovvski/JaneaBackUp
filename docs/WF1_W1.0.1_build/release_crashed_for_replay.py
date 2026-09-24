#!/usr/bin/env python3
"""Release the 32 crashed SENT events in WF-2S so the reconciler re-detects them.

The correction this implements: "unclaimed in WF-2" is not the same as "will be retried". Recovery
needs BOTH stores to agree the work is outstanding -
  * WF-2   wf2_seen        - unclaimed (P0-1b did its job; nothing will double-process)
  * WF-2S  __sent_seen_v2  - marked SEEN, because Summary writes it on having SENT the replay,
                             not on WF-2 having succeeded. So WF-2S thinks it is done.
Releasing the WF-2S side is what actually makes them replayable.

Keyed by `stats_id` (Find New Sends: `const key = h.stats_id`), verified present for all 32.

Safe because the WF-2 side is still unclaimed: when these replay, Dedupe sees an unclaimed key and
processes them once. Bursts are now spaced 10s and Pipedrive calls retry 5x@5s, so the condition
that crashed them is gone.
"""
import argparse, copy, json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
SINCE = datetime.fromisoformat("2026-08-11T14:30:00+00:00")
NOW = datetime.now(timezone.utc)


def n8n(p, q=None, method="GET", body=None, attempt=0):
    import time
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(p, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {p} FAILED: HTTP {e.code}")


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": "error"})
targets, unclaimed_ok = {}, 0
w2 = n8n(f"/api/v1/workflows/{WF2}")
wseen = ((w2.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
for e in ((p or {}).get("data") or []):
    if (ts(e.get("startedAt")) or SINCE) < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
        ded = rd["Dedupe"][0]["data"]["main"][0][0]["json"]
        wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    if nm.get("event") != "SENT":
        continue
    body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
    sid = (body or {}).get("stats_id")
    dk = ded.get("__dedupe_key")
    if not sid:
        continue
    # only release events whose WF-2 side is genuinely OUTSTANDING - never one already claimed,
    # or the replay would duplicate work that already happened.
    if dk and dk in wseen:
        print(f"   SKIP {sid} - WF-2 side already claimed ({dk})")
        continue
    unclaimed_ok += 1
    targets[sid] = {"exec": e["id"], "email": (nm.get("lead") or {}).get("email"), "key": dk}

ws = n8n(f"/api/v1/workflows/{WF2S}")
WSO = copy.deepcopy(ws)
sd = (ws.get("staticData") or {}).get("global") or {}
seen = dict(sd.get("__sent_seen_v2") or {})
present = [s for s in targets if s in seen]

# ---------------------------------------------------------------- ROTATION / WINDOW FILTER
# Two separate windows, and confusing them is how "released" becomes a lie:
#   * WF-2's dedupe rotates at dedupe_max_age_sec (48h) - past that, absence is EXPIRY not loss
#     (section 9b.0e). Releasing such a key changes nothing.
#   * WF-2S only DETECTS sends inside its own lookback_minutes. A key released for an event older
#     than that is released into a window the reconciler never looks at - the release succeeds and
#     recovers nothing. That is reported, never silently performed.
import re as _re
_raw = json.dumps((next((n for n in ws["nodes"] if n["name"] == "CONFIG"), {}) or {})
                  .get("parameters") or {})
_look = int((_re.search(r'\\"lookback_minutes\\":\s*(\d+)', _raw) or [0, 180])[1])
print(f"\nWF-2S lookback_minutes = {_look}  (its detection window)")
def _event_age_min(rec):
    """Age of the EVENT, not of the execution.

    `startedAt` is null on some execution rows (n8n leaves it unset on certain failures - the same
    nulls that produced a phantom "16 new errors" earlier). The dedupe key carries the authoritative
    instant as trailing epoch-ms: `SENT|<campaign>|<lead>|<epoch_ms>`. WF-2S's lookback compares
    against Smartlead's send time, so the key is also the RIGHT clock, not merely the available one.
    """
    k = rec.get("key") or ""
    tail = str(k).rsplit("|", 1)[-1]
    if tail.isdigit() and len(tail) >= 12:
        return (NOW - datetime.fromtimestamp(int(tail) / 1000, timezone.utc)).total_seconds() / 60
    t = ts(rec.get("at"))
    return ((NOW - t).total_seconds() / 60) if t else None


actionable, aged_out = [], []
for s in present:
    age_min = _event_age_min(targets[s])
    (actionable if (age_min is not None and age_min <= _look) else aged_out).append(
        (s, age_min))
def _age(a):
    # an unknown age is NOT treated as in-window: unknown must never take the permissive branch,
    # which is the null-defaults-to-pass shape that produced two false alarms already.
    return f"{a:.0f} min" if isinstance(a, (int, float)) else "age UNKNOWN"


for s, age in aged_out:
    print(f"   AGED OUT  {s}  event {_age(age)} > {_look} min lookback "
          f"({targets[s]['email']})")
for s, age in actionable:
    print(f"   in window {s}  {_age(age)} ({targets[s]['email']})")
if aged_out and not actionable:
    print("\n*** every candidate is outside WF-2S's detection window. Releasing the key would")
    print("    succeed and recover NOTHING - the reconciler does not look that far back.")
    print("    Options: raise lookback_minutes for one cycle, or replay the event directly.")
present = [s for s, _ in actionable]
print(f"\ncrashed SENT with an outstanding WF-2 side : {unclaimed_ok}")
print(f"of those, currently blocked in __sent_seen_v2: {len(present)}")
print(f"__sent_seen_v2 before: {len(seen)}")
for s in present[:5]:
    print(f"   release {s}  ({targets[s]['email']})")
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)
if not present:
    print("\nnothing to release.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2s_backup_before_release_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(WSO, indent=2, ensure_ascii=False))

fresh = ((n8n(f"/api/v1/workflows/{WF2S}").get("staticData") or {}).get("global") or {})
fseen = dict(fresh.get("__sent_seen_v2") or {})
for s in present:
    fseen.pop(s, None)
body = put_body(ws)
body["staticData"] = {"global": {**fresh, "__sent_seen_v2": fseen}}
d = stripped_keys(ws)
if d:
    print(f"stripping {d}")
n8n(f"/api/v1/workflows/{WF2S}", None, "PUT", body)

after = n8n(f"/api/v1/workflows/{WF2S}")
aseen = ((after.get("staticData") or {}).get("global") or {}).get("__sent_seen_v2") or {}
still = [s for s in present if s in aseen]
print(f"\nlive verification: {'CLEAN' if not still else 'PROBLEMS'}")
for s in still:
    print(f"  - not released: {s}")
print(f"  WF-2S versionId={after.get('versionId')} active={after.get('active')} "
      f"__sent_seen_v2={len(aseen)} (was {len(seen)})")
print(f"  released {len(present)} -> WF-2S will re-detect them next cycle, "
      f"{20} per cycle, spaced 10s")
sys.exit(1 if still else 0)
