#!/usr/bin/env python3
"""B5 - switch the legacy Make scenarios OFF, in order, each verified by read-back.

  8557031  lead creation            -> OFF first, so the next send flows through us only
  8557478  responded label+forwards -> OFF second, so forwarding runs off our map only

Order matters and is not cosmetic: killing the forwarder first would leave Make still creating
leads with an empty Campaign field (its known defect) while nothing forwarded. Lead creation goes
first.

Zapier label zaps are NOT touched - separate track, pending the 274318213 verdict.

Each step: read state -> stop -> re-read -> assert isActive is False. A stop that is not verified
by an independent read is not a kill.

DRY_RUN=1 default. Rollback is the same call with /start.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = [(8557031, "lead creation"), (8557478, "responded label + forwards")]


def mk(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    url = f"https://{ZONE}.make.com/api/v2{path}"
    try:
        r = urllib.request.Request(url, method=method, data=data,
                                   headers={"Authorization": f"Token {MTOK}",
                                            "Content-Type": "application/json",
                                            "User-Agent": "janea-b5/1.0"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            raw = x.read()
            try:
                return {"__status": x.status, "body": json.loads(raw)}
            except Exception:
                return {"__status": x.status, "raw": raw.decode("utf-8", "replace")[:200]}
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return {"__err": str(e)[:200]}


def state(sid):
    d = mk(f"/scenarios/{sid}")
    s = (d.get("body") or {}).get("scenario") or {}
    return s.get("isActive"), s.get("name")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
ap.add_argument("--rollback", action="store_true", help="turn both back ON")
a = ap.parse_args()

print(f"B5 {'ROLLBACK' if a.rollback else 'KILL'} "
      f"{'(LIVE)' if a.deploy else '(DRY-RUN)'}  {datetime.now(timezone.utc).isoformat()}\n")

results = []
targets = list(reversed(ORDER)) if a.rollback else ORDER
for sid, label in targets:
    active, name = state(sid)
    want = True if a.rollback else False
    print(f"{sid}  {label}")
    print(f"   name        : {name!r}")
    print(f"   isActive now: {active}   -> target {want}")
    if active == want:
        print("   already in target state")
        results.append({"id": sid, "action": "noop", "isActive": active})
        continue
    if not a.deploy:
        print(f"   DRY-RUN: would POST /scenarios/{sid}/{'start' if a.rollback else 'stop'}")
        results.append({"id": sid, "action": "would-change", "isActive": active})
        continue

    r = mk(f"/scenarios/{sid}/{'start' if a.rollback else 'stop'}", "POST", {})
    if r.get("__err"):
        print(f"   CALL FAILED: {r.get('__err')} {str(r.get('__body'))[:160]}")
        results.append({"id": sid, "action": "failed", "error": r.get("__err")})
        print("\n   STOPPING - not proceeding to the next scenario after a failure")
        break
    time.sleep(2)
    after, _ = state(sid)                      # independent read-back, not the call's own answer
    ok = after is want
    print(f"   read-back   : isActive={after}  {'VERIFIED' if ok else 'MISMATCH'}")
    results.append({"id": sid, "action": "changed", "isActive_after": after, "verified": ok})
    if not ok:
        print("\n   STOPPING - read-back did not confirm the change")
        break

print("\n--- summary ---")
for r in results:
    print("  ", json.dumps(r, default=str))
allok = all(r.get("action") in ("noop", "would-change")
            or r.get("verified") for r in results) and len(results) == len(targets)
print(f"\nB5: {'GREEN' if allok else 'INCOMPLETE'}")
if a.deploy and not a.rollback and allok:
    print("\nROLLBACK COMMAND:  python b5_kill_make.py --rollback --deploy")
json.dump({"at": datetime.now(timezone.utc).isoformat(), "rollback": a.rollback,
           "deploy": a.deploy, "results": results},
          open(os.path.join(HERE, "wf1-release-evidence", "b5_kill_make.json"), "w",
               encoding="utf-8"), indent=2, default=str)
sys.exit(0 if allok else 1)
