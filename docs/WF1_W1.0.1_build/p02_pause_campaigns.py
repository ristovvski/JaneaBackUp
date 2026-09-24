#!/usr/bin/env python3
"""P0-2 step 1 - PAUSE the four Ai4 campaigns.

Stops the accumulation of un-recorded sends (242 today, rows still arriving at 15:54Z) with zero
deploy risk. Not a fix - a tourniquet. The fix is WF-2S onto leads-statistics history[] type=SENT,
after which these get unpaused.

Deliberately NOT re-enabling Make 8557031: it writes leads with an empty Campaign field, which
breaks W1.0.11 lead-per-campaign matching and duplicates leads. Accumulating backfillable sends is
the recoverable failure; injecting duplicate leads is not.

Each pause is verified by an independent status re-read.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
CAMPS = {3686181: "Mario-Valids", 3686184: "Mario-Catch-alls",
         3686187: "Rune-Valids", 3686193: "Rune-Catch-alls"}


def sl(path, params=None, method="GET", body=None):
    q = dict(params or {}); q["api_key"] = SLK
    data = json.dumps(body).encode() if body is not None else None
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    try:
        r = urllib.request.Request(url, method=method, data=data,
                                   headers={"User-Agent": "janea-p02/1.0",
                                            "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            raw = x.read()
            try:
                return json.loads(raw)
            except Exception:
                return {"__status": x.status, "raw": raw.decode("utf-8", "replace")[:200]}
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:250]}
    except Exception as e:
        return {"__err": str(e)[:200]}


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
ap.add_argument("--resume", action="store_true", help="set back to START (after the WF-2S fix)")
a = ap.parse_args()
# The API COMMAND and the reported STATUS differ: you POST 'START', the campaign then reads back
# as 'ACTIVE'. Comparing the read-back against the command produced a false MISMATCH and (correctly)
# stopped the run after the first campaign.
command = "START" if a.resume else "PAUSED"
target = "ACTIVE" if a.resume else "PAUSED"

print(f"{'RESUME' if a.resume else 'PAUSE'} four Ai4 campaigns  "
      f"{datetime.now(timezone.utc).isoformat()}\n")
results = []
for cid, label in CAMPS.items():
    c = sl(f"/campaigns/{cid}")
    before = str((c or {}).get("status") or "?").upper()
    print(f"{cid}  {label:<18} status={before}  -> target {target}")
    if before == target:
        print("    already in target state")
        results.append({"id": cid, "before": before, "after": before, "changed": False})
        continue
    if not a.deploy:
        print(f"    DRY-RUN: would POST /campaigns/{cid}/status status={command}")
        results.append({"id": cid, "before": before, "would": target})
        continue
    r = sl(f"/campaigns/{cid}/status", None, "POST", {"status": command})
    if r.get("__err"):
        print(f"    CALL FAILED: {r.get('__err')} {str(r.get('__body'))[:160]}")
        results.append({"id": cid, "before": before, "error": r.get("__err")})
        print("    STOPPING - not proceeding to the next campaign after a failure")
        break
    time.sleep(2)
    after = str((sl(f"/campaigns/{cid}") or {}).get("status") or "?").upper()
    ok = after == target
    print(f"    read-back: status={after}  {'VERIFIED' if ok else 'MISMATCH'}")
    results.append({"id": cid, "before": before, "after": after, "verified": ok})
    if not ok:
        print("    STOPPING - read-back did not confirm")
        break

done = [r for r in results if r.get("verified") or r.get("changed") is False]
print(f"\n{'RESUME' if a.resume else 'PAUSE'}: {len(done)}/{len(CAMPS)} campaigns in target state")
if a.deploy:
    print(f"REVERSE COMMAND: python p02_pause_campaigns.py "
          f"{'--deploy' if a.resume else '--resume --deploy'}")
json.dump({"at": datetime.now(timezone.utc).isoformat(), "target": target, "results": results},
          open(os.path.join(HERE, "wf1-release-evidence",
                            f"p02_{'resume' if a.resume else 'pause'}.json"), "w",
               encoding="utf-8"), indent=2, default=str)
sys.exit(0 if len(done) == len(CAMPS) else 1)
