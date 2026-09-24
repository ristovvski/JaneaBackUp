#!/usr/bin/env python3
"""FIRE — relink 70 orphaned Finovate leads + rename 70 email-named persons.

Two fields only: lead.person_id and person first/last. Nothing else touched.

DISCIPLINE (same shape as the 215 repair):
  * snapshot both fields for every record BEFORE any write
  * chunked, so a mid-run failure leaves a readable boundary
  * PER-RECORD GUARD RE-CHECK at write time: skip a lead that has since gained a person, and skip a
    person whose name is no longer the email (a human got there first)
  * post-run verification: zero Finovate orphans remain, zero email-named persons remain

Names are sent as the first/last PAIR - Pipedrive rejects `name` together with the parts, and the
parts are the structured truth (learned when the first 215-repair attempt was refused wholesale).
"""
import argparse, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--chunk", type=int, default=20)
a = ap.parse_args()


def pd(p, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + p, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": f"HTTP {e.code} {e.read()[:220].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"__err": str(e)[:140]}


PLAN = json.load(open(os.path.join(HERE, "orphan_repair_map.json"), encoding="utf-8"))["plan"]
print(f"plan: {len(PLAN)} leads to relink, "
      f"{sum(1 for x in PLAN if x['needs_rename'])} persons to rename")
stamp = int(datetime.now(timezone.utc).timestamp())

if not a.live:
    for x in PLAN[:5]:
        print(f"  lead {str(x['lead_id'])[:8]} -> person {x['person_id']}  "
              f"({x['person_name_now']!r} -> {x['first']} {x['last']})")
    print("\n--live not given: NOTHING WRITTEN.")
    sys.exit(0)

# ---- snapshot
print("\nsnapshotting...")
snap = {"leads": {}, "persons": {}}
for i, x in enumerate(PLAN, 1):
    l = (pd(f"/v1/leads/{x['lead_id']}") or {}).get("data") or {}
    snap["leads"][str(x["lead_id"])] = {"person_id": l.get("person_id"),
                                        "title": l.get("title")}
    p = (pd(f"/api/v2/persons/{x['person_id']}") or {}).get("data") or {}
    snap["persons"][str(x["person_id"])] = {"name": p.get("name"),
                                            "first_name": p.get("first_name"),
                                            "last_name": p.get("last_name")}
    if i % 25 == 0:
        print(f"  ...{i}/{len(PLAN)}")
sp = os.path.join(HERE, f"orphan_repair_snapshot_{stamp}.json")
json.dump(snap, open(sp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"snapshot: {os.path.basename(sp)}")

relinked = renamed = 0
skipped, failed = [], []
print(f"\nwriting in chunks of {a.chunk}...")
for start in range(0, len(PLAN), a.chunk):
    for x in PLAN[start:start + a.chunk]:
        # GUARD 1 — lead must still be orphaned
        l = (pd(f"/v1/leads/{x['lead_id']}") or {}).get("data") or {}
        if l.get("person_id"):
            skipped.append({"lead_id": x["lead_id"], "why": "already has a person",
                            "now": l.get("person_id")})
        else:
            r = pd(f"/v1/leads/{x['lead_id']}", "PATCH", {"person_id": x["person_id"]})
            if r.get("__err"):
                failed.append({"lead_id": x["lead_id"], "err": r["__err"][:110]})
            else:
                relinked += 1
        # GUARD 2 — person name must still be the email
        if not x["needs_rename"]:
            continue
        p = (pd(f"/api/v2/persons/{x['person_id']}") or {}).get("data") or {}
        if str(p.get("name") or "") != x["email"]:
            skipped.append({"person_id": x["person_id"], "why": "name changed since map",
                            "now": p.get("name")})
            continue
        r2 = pd(f"/api/v2/persons/{x['person_id']}", "PATCH",
                {"first_name": x["first"], "last_name": x["last"]})
        if r2.get("__err"):
            failed.append({"person_id": x["person_id"], "err": r2["__err"][:110]})
        else:
            renamed += 1
    print(f"  chunk {start // a.chunk + 1}: relinked={relinked} renamed={renamed} "
          f"skipped={len(skipped)} failed={len(failed)}")
    time.sleep(1)

print(f"\nWROTE  relinked={relinked}  renamed={renamed}")
print(f"guard skips: {len(skipped)}   failures: {len(failed)}")
for f in failed[:5]:
    print("   FAIL", f)

# ---- verification
print("\n--- verification ---")
still_orphan, still_email = [], []
for x in PLAN:
    l = (pd(f"/v1/leads/{x['lead_id']}") or {}).get("data") or {}
    if not l.get("person_id"):
        still_orphan.append(x["lead_id"])
    p = (pd(f"/api/v2/persons/{x['person_id']}") or {}).get("data") or {}
    if str(p.get("name") or "") == x["email"]:
        still_email.append(x["person_id"])
print(f"  leads still orphaned        : {len(still_orphan)}")
print(f"  persons still named by email: {len(still_email)}")

# a fresh sweep, not just the planned set - proves the CLASS is empty
sweep, start = [], 0
while start < 600:
    r = pd(f"/v1/leads?limit=100&start={start}&sort=add_time%20DESC")
    rows = (r or {}).get("data") or []
    if not rows:
        break
    for y in rows:
        t = str(y.get("title") or "")
        if (t.startswith("3868449 - ") or t.startswith("3868450 - ")) and not y.get("person_id"):
            sweep.append(y.get("id"))
    more = ((r.get("additional_data") or {}).get("pagination") or {})
    if not more.get("more_items_in_collection"):
        break
    start = more.get("next_start") or (start + 100)
print(f"  FRESH SWEEP, Finovate orphans anywhere: {len(sweep)}")
json.dump({"relinked": relinked, "renamed": renamed, "skipped": skipped, "failed": failed,
           "still_orphan": still_orphan, "still_email": still_email, "sweep": sweep},
          open(os.path.join(HERE, f"orphan_repair_result_{stamp}.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"\nresult: orphan_repair_result_{stamp}.json")
