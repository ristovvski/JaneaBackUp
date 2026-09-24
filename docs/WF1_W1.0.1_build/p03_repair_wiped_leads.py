#!/usr/bin/env python3
"""P0-3 step 2 - repair the 11 wiped leads from the auditor's a8_handover.json.

ORDERING: the four label-writing zaps were killed FIRST (16:11-16:12Z, read-back verified). Repairing
while they were live meant any person-update would re-trigger the overwrite.

UNION semantics: restore what was lost, never remove what exists. Target = union(live labels now,
auditor's target_label_ids). Re-reads each lead live rather than trusting the snapshot - the file
was written at 15:56Z and the world has moved.

Expect ~5 Handover activities to mint on the leads regaining '3. Responded'. That is Melisa's
automation working; they are left in place per instruction, and counted for Nik's heads-up.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
HANDOVER = (r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------"
            r"\058d1620-6d1d-469c-a969-e74b9f34d6fd\scratchpad\a8_handover.json")
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NAMES = {"a6d359b0-6a45-11ed-ab46-5b95b19fcb18": "1. Cold",
         "ca698a50-bdfb-11ef-8172-510383583b0e": "2. Connected",
         "c9d4b550-bcf3-11ef-a843-357f91e826ec": "3. Responded",
         "3198a520-d19e-11ef-b90a-f3c01a30f7ae": "4. Positive Reply",
         "5f022d10-0f6f-11f0-99e2-d33e09d9138e": "AUTOMATED LEAD NURTURING"}


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea-p03/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:250]}


def nm(ids):
    return [NAMES.get(x, x) for x in (ids or [])]


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

repairs = json.load(open(HANDOVER, encoding="utf-8"))["repairs"]
print(f"repairs in handover: {len(repairs)}   mode: {'LIVE' if a.deploy else 'DRY-RUN'}\n")

results, will_regain_responded = [], []
for rep in repairs:
    lid = rep["lead_id"]
    L = (pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    if not L:
        print(f"  {lid[:8]}  UNREADABLE - skipping")
        results.append({"lead": lid, "status": "unreadable"})
        continue
    live = list(L.get("label_ids") or [])
    target = list(rep["target_label_ids"])
    union = live[:]
    for x in target:
        if x not in union:
            union.append(x)
    missing = [x for x in target if x not in live]
    print(f"  {lid[:8]}  {str(rep.get('title'))[:38]:<38}")
    print(f"      live   : {nm(live)}")
    print(f"      target : {nm(target)}")
    if not missing:
        print("      already correct - no patch")
        results.append({"lead": lid, "status": "already_ok", "labels": live})
        continue
    print(f"      RESTORE: {nm(missing)}")
    if RESPONDED in missing:
        will_regain_responded.append(lid)
    if not a.deploy:
        results.append({"lead": lid, "status": "would_patch", "restore": missing})
        continue
    r = pd(f"/v1/leads/{lid}", "PATCH", {"label_ids": union})
    if r.get("__err"):
        print(f"      PATCH FAILED: {r.get('__err')} {str(r.get('__body'))[:120]}")
        results.append({"lead": lid, "status": "failed", "error": r.get("__err")})
        continue
    time.sleep(1)
    back = (pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    now = back.get("label_ids") or []
    ok = all(x in now for x in target)
    print(f"      read-back: {nm(now)}  {'VERIFIED' if ok else 'MISMATCH'}")
    results.append({"lead": lid, "status": "repaired" if ok else "mismatch", "labels": now})

done = [r for r in results if r["status"] in ("repaired", "already_ok")]
print(f"\nrepaired/ok: {len(done)}/{len(repairs)}")
print(f"leads regaining '3. Responded' (expect a Handover mint each): "
      f"{len(will_regain_responded)}")

if a.deploy and will_regain_responded:
    print("\nwaiting 45s, then counting Handover activities minted on those leads...")
    time.sleep(45)
    minted = []
    for lid in will_regain_responded:
        acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=50") or {}).get("data") or []
        fresh = [x for x in acts if str(x.get("type")) == "handover"
                 and str(x.get("add_time") or "") >= "2026-08-10T16:1"]
        for x in fresh:
            minted.append({"lead": lid, "activity": x["id"], "add_time": x.get("add_time")})
            print(f"   Handover {x['id']} on {lid[:8]} at {x.get('add_time')}")
    print(f"  Handover activities minted: {len(minted)} (left in place by instruction)")
else:
    minted = []

json.dump({"at": datetime.now(timezone.utc).isoformat(), "results": results,
           "responded_restored": will_regain_responded, "handovers_minted": minted},
          open(os.path.join(HERE, "wf1-release-evidence", "p03_repair.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if len(done) == len(repairs) else 1)
