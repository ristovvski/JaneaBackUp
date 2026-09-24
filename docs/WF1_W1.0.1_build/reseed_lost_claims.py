#!/usr/bin/env python3
"""RE-SEED every claim the staticData race lost. Reconstructed from evidence, not from the auditor's
file - so his list and mine are independent and can be cross-checked rather than echoed.

The race (his diagnosis): n8n persists $getWorkflowStaticData('global') ONCE at execution end, as a
whole object. Overlapping executions each load a snapshot and the last finisher overwrites the
others wholesale - so a claim can be lost even though its node ran perfectly. Bursts are now spaced,
so nothing NEW should be lost; but everything already lost is still armed, and unclaimed events
inside WF-2R's 48h reach are exactly the duplicate-forward route.

Three claim families, each rebuilt from what actually happened:

  1. __alert_delivered  - an execution whose `Reply Alert` returned ok:true DID deliver. Its
                          __alert_key belongs in the registry. Missing => lost to the race.
  2. F|<dedupe_key>     - an execution whose `SL Forward Email` returned ok:true DID send mail.
                          Missing => a replay would send it AGAIN.
  3. wf2_seen           - an execution that SUCCEEDED did its work. Missing => it will replay.
                          CRASHED executions are deliberately left unclaimed: they did NOT finish,
                          and P0-1b's whole value is that they stay replayable.

That third rule is the one to get right. Re-seeding a crashed event would silently discard it -
the precise failure P0-1b exists to prevent - so status is checked per execution, never assumed.
"""
import argparse, json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
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

ids, cursor = [], None
while True:
    q = {"workflowId": WF2, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += [(e["id"], e.get("status"), e.get("startedAt")) for e in (p.get("data") or [])]
    cursor = p.get("nextCursor")
    if not cursor:
        break
print(f"WF-2 executions to inspect: {len(ids)}")

want_alert, want_fwd, want_seen, crashed_left = {}, {}, {}, []
for i, (eid, status, started) in enumerate(ids, 1):
    if i % 100 == 0:
        print(f"  ...{i}/{len(ids)}", flush=True)
    det = n8n(f"/api/v1/executions/{eid}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})

    def o(nm, k=None):
        try:
            j = rd[nm][0]["data"]["main"][0][0]["json"]
            return j if k is None else j.get(k)
        except Exception:
            return None

    ded = o("Dedupe", "__dedupe_key")
    alert = o("Reply Alert") or {}
    fwd = o("SL Forward Email") or {}
    akey = o("First Reply Gate", "__alert_key")
    if alert.get("ok") is True and akey:
        want_alert.setdefault(str(akey), started)
    if fwd.get("ok") is True and ded:
        want_fwd.setdefault(f"F|{ded}", started)
    if ded:
        if status == "success":
            want_seen.setdefault(ded, started)
        else:
            crashed_left.append((eid, ded, status))

wf = n8n(f"/api/v1/workflows/{WF2}")
sd = (wf.get("staticData") or {}).get("global") or {}
seen = dict(sd.get("wf2_seen") or {})
alert_reg = dict(sd.get("__alert_delivered") or {})

# ---------------------------------------------------------------- two corrections to the naive rule
#
# (1) ROTATION IS NOT LOSS. `Dedupe` prunes wf2_seen entries older than dedupe_max_age_sec (48h).
#     Across 597 executions spanning weeks, most keys are absent because they were correctly rotated
#     out. Counting those as "lost to the race" produced 340 instead of the auditor's 42. Only the
#     48h window is meaningful - and it is also the only window in which a replay can happen at all.
#
# (2) DELIBERATE RELEASES MUST NOT BE RE-SEEDED. Several keys are missing because I removed them
#     ON PURPOSE tonight. Re-seeding them would silently reverse the evening's repairs:
#       * the three OOO leads' alert slots - released so the humans' real reply on their return
#         still alerts as their first. Re-seeding re-mutes three real prospects.
#       * person 84885 - the fixture's slot, released for the retest.
#       * Marine's dedupe key - released precisely SO WF-2R replays her. Re-seeding cancels the
#         recovery we chose.
#     An automated repair that undoes a deliberate decision is worse than no repair.
DELIBERATE = {
    "REPLIED|3686187|4306240392|1786452347000",      # fixture specimen, released for replay
    "REPLIED|3686184|4214180591|1786375820000",      # Marine - released ON PURPOSE
    "84885",                                          # fixture person alert slot
    "4ead0900-90d6-11f1-b07d-7faf1dbb463a",           # pii-d5d243f4@example.invalid  - OOO slot released
    "51c9f9d0-8538-11f1-8c6a-ef2edb9d15ea",           # pii-9f313a1a@example.invalid - OOO slot released
    "17c6d0b0-8541-11f1-998a-a9f867fdc12c",           # william.kinney   - OOO slot released
}
WINDOW = timedelta(hours=48)


def recent(v):
    t = ts(v)
    return bool(t) and (NOW - t) < WINDOW


miss_alert = {k: v for k, v in want_alert.items()
              if k not in alert_reg and k not in DELIBERATE}
miss_fwd = {k: v for k, v in want_fwd.items()
            if k not in seen and k not in DELIBERATE}
miss_seen = {k: v for k, v in want_seen.items()
             if k not in seen and k not in DELIBERATE and recent(v)}
rotated = sum(1 for k, v in want_seen.items() if k not in seen and not recent(v))
held_back = sum(1 for k in list(want_alert) + list(want_seen) if k in DELIBERATE)
print(f"\n  excluded as ROTATION (older than 48h, correctly pruned): {rotated}")
print(f"  excluded as DELIBERATE RELEASES (would undo tonight's repairs): {held_back}")
print(f"\n--- reconstructed vs live ---")
print(f"  delivered alerts on the wire : {len(want_alert):>4}   missing from registry: {len(miss_alert)}")
print(f"  forwards sent on the wire    : {len(want_fwd):>4}   missing F-keys       : {len(miss_fwd)}")
print(f"  successful executions        : {len(want_seen):>4}   missing dedupe keys  : {len(miss_seen)}")
print(f"  crashed/errored (LEFT UNCLAIMED on purpose): {len(crashed_left)}")
total = len(miss_alert) + len(miss_fwd) + len(miss_seen)
print(f"  TOTAL claims lost to the race: {total}   (auditor's count: 42)")

inside = [k for k, v in miss_seen.items()
          if (t := ts(v)) and (NOW - t) < timedelta(hours=48)]
print(f"  of the missing dedupe keys, INSIDE WF-2R's 48h reach (armed to replay): {len(inside)}")
for k in list(miss_alert)[:6]:
    print(f"     alert  {k}")
for k in list(miss_fwd)[:6]:
    print(f"     fwd    {k}")
for k in list(miss_seen)[:8]:
    print(f"     seen   {k}")

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)
if not total:
    print("\nnothing to re-seed.")
    sys.exit(0)

now_s = int(NOW.timestamp())
fresh = ((n8n(f"/api/v1/workflows/{WF2}").get("staticData") or {}).get("global") or {})
fseen = dict(fresh.get("wf2_seen") or {})
falert = dict(fresh.get("__alert_delivered") or {})
for k in list(miss_fwd) + list(miss_seen):
    fseen.setdefault(k, now_s)
for k in miss_alert:
    falert.setdefault(k, now_s)
body = put_body(wf)
body["staticData"] = {"global": {**fresh, "wf2_seen": fseen, "__alert_delivered": falert}}
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2}", None, "PUT", body)

after = n8n(f"/api/v1/workflows/{WF2}")
asd = (after.get("staticData") or {}).get("global") or {}
aseen, aalert = asd.get("wf2_seen") or {}, asd.get("__alert_delivered") or {}
problems = [k for k in list(miss_fwd) + list(miss_seen) if k not in aseen]
problems += [k for k in miss_alert if k not in aalert]
# the crashed events must STILL be unclaimed - re-seeding one would silently discard it
wrongly = [d for (_e, d, _s) in crashed_left if d in aseen and d not in want_seen]
print(f"\nlive verification: {'CLEAN' if not problems and not wrongly else 'PROBLEMS'}")
for p in problems:
    print(f"  - not seeded: {p}")
for w in wrongly:
    print(f"  - *** crashed event wrongly claimed: {w}")
print(f"  versionId={after.get('versionId')} active={after.get('active')}")
print(f"  wf2_seen={len(aseen)} (F-keys {len([k for k in aseen if k.startswith('F|')])})  "
      f"__alert_delivered={len(aalert)}")
print(f"  crashed events still replayable: "
      f"{sum(1 for (_e, dk, _s) in crashed_left if dk not in aseen)}/{len(crashed_left)}")
sys.exit(1 if (problems or wrongly) else 0)
