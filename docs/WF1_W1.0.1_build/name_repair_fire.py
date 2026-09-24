#!/usr/bin/env python3
"""215-name repair, STEP 2 — FIRE. Renames persons and retitles leads from provider truth.

Option (a), Nik: provider truth only. The 15 LinkedIn-abbreviated surnames ship as the provider
holds them. **No name is ever derived from an email address again, by any algorithm** — that rule is
why option (b) was declined.

SCOPE, deliberately narrow: person `name` and lead `title`. NOT company — the map carries a provider
company but at least one is inconsistent with the address (pii-bc41bcbd@example.invalid -> "HSBC"), and
nothing about this repair requires touching it.

DISCIPLINE:
  * snapshot every person + lead BEFORE any write (the bracket's opening)
  * chunked, so a mid-run failure leaves a readable boundary rather than an unknown state
  * PER-RECORD GUARD RE-CHECK at write time, not just at map-build time: a record whose name is no
    longer the email local-part has been touched by a human since, and is skipped
  * post-run verification: zero name==local-part remaining, zero pre-existing corrections disturbed
"""
import argparse, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--chunk", type=int, default=25)
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


R = json.load(open(os.path.join(HERE, "name_repair_map.json"), encoding="utf-8"))["renameable"]
print(f"map: {len(R)} persons, {sum(len(x['leads']) for x in R)} lead titles")
stamp = int(datetime.now(timezone.utc).timestamp())

if not a.live:
    print("\n--live not given. Preview:")
    for x in R[:5]:
        print(f"  person {x['person_id']}: {x['old_name']!r} -> {x['new_name']!r}")
        for l in x["leads"]:
            print(f"     lead {str(l['lead_id'])[:8]}: ...{l['old_title'][-46:]!r}")
    sys.exit(0)

# ---- snapshot BEFORE anything
snap = {"persons": {}, "leads": {}}
print("\nsnapshotting current state...")
for i, x in enumerate(R, 1):
    p = (pd(f"/api/v2/persons/{x['person_id']}") or {}).get("data") or {}
    snap["persons"][str(x["person_id"])] = {"name": p.get("name"),
                                            "first_name": p.get("first_name"),
                                            "last_name": p.get("last_name")}
    for l in x["leads"]:
        ld = (pd(f"/v1/leads/{l['lead_id']}") or {}).get("data") or {}
        snap["leads"][str(l["lead_id"])] = {"title": ld.get("title")}
    if i % 50 == 0:
        print(f"  ...{i}/{len(R)}")
snap_path = os.path.join(HERE, f"name_repair_snapshot_{stamp}.json")
json.dump(snap, open(snap_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"snapshot: {os.path.basename(snap_path)}")

renamed = retitled = 0
skipped_guard = []
failed = []
print(f"\nwriting in chunks of {a.chunk}...")
for start in range(0, len(R), a.chunk):
    chunk = R[start:start + a.chunk]
    for x in chunk:
        pid = x["person_id"]
        cur = (pd(f"/api/v2/persons/{pid}") or {}).get("data") or {}
        cur_name = str(cur.get("name") or "")
        # GUARD, re-checked at write time
        if cur_name != x["local_part"]:
            skipped_guard.append({"person_id": pid, "email": x["email"],
                                  "name_now": cur_name, "expected": x["local_part"]})
            continue
        # Pipedrive rejects `name` together with first/last: "Cannot set 'name' and
        # 'first_name'/'last_name' at the same time." Send the PAIR — it is the structured truth and
        # Pipedrive derives the display name from it. Falls back to `name` only if the provider gave
        # no surname (none do in this map, but the branch keeps the script honest if reused).
        body = ({"first_name": x["first_name"], "last_name": x["last_name"]}
                if x["first_name"] and x["last_name"] else {"name": x["new_name"]})
        r1 = pd(f"/api/v2/persons/{pid}", "PATCH", body)
        if r1.get("__err"):
            failed.append({"person_id": pid, "err": r1["__err"]})
            continue
        renamed += 1
        for l in x["leads"]:
            ld = (pd(f"/v1/leads/{l['lead_id']}") or {}).get("data") or {}
            if str(ld.get("title") or "") != l["old_title"]:
                skipped_guard.append({"lead_id": l["lead_id"], "reason": "title changed since map"})
                continue
            r2 = pd(f"/v1/leads/{l['lead_id']}", "PATCH", {"title": l["new_title"]})
            if r2.get("__err"):
                failed.append({"lead_id": l["lead_id"], "err": r2["__err"]})
            else:
                retitled += 1
    print(f"  chunk {start // a.chunk + 1}: renamed={renamed} retitled={retitled} "
          f"skipped={len(skipped_guard)} failed={len(failed)}")
    time.sleep(1)

print(f"\nWROTE persons={renamed}  lead titles={retitled}")
print(f"guard skips: {len(skipped_guard)}   failures: {len(failed)}")
for f in failed[:5]:
    print("   FAIL", f)

# ---- post-run verification
print("\n--- verification ---")
still_bad = []
disturbed = []
for x in R:
    p = (pd(f"/api/v2/persons/{x['person_id']}") or {}).get("data") or {}
    now = str(p.get("name") or "")
    if now == x["local_part"]:
        still_bad.append(x["email"])
    was = snap["persons"].get(str(x["person_id"]), {}).get("name")
    if was != x["local_part"] and now != was:
        disturbed.append({"person_id": x["person_id"], "was": was, "now": now})
print(f"  records still showing name == email local-part: {len(still_bad)}")
if still_bad[:5]:
    print(f"    {still_bad[:5]}")
print(f"  hand-corrected records disturbed: {len(disturbed)}")
for d in disturbed[:5]:
    print("   ", d)
json.dump({"renamed": renamed, "retitled": retitled, "skipped_guard": skipped_guard,
           "failed": failed, "still_bad": still_bad, "disturbed": disturbed},
          open(os.path.join(HERE, f"name_repair_result_{stamp}.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"\nresult: name_repair_result_{stamp}.json")
