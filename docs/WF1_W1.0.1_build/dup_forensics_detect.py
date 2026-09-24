"""DUPLICATE FORENSICS step 2+3 - consumes the harvested Slack dataset, detects duplicates, and
diagnoses each via the Pipedrive person changelog (the method proven twice today: person's field
history vs the exact post timestamp, change_source/user_agent/actor_user_id as the fingerprint).

Duplicate definition: same lead_uuid + same template, posts within a window.
  - PRIMARY: gap <= 120s
  - NEAR:    120s < gap <= 24h  (reported separately per the owner's framing)
  - REPEAT:  gap > 24h          (different-day repeats - a different disease, reported separately)

Diagnosis per duplicate pair, using the changelog:
  - class A: TWO separate Pipedrive writes precede the two posts (per-event firing - working as
             designed, if noisy)
  - class B: ONE write precedes BOTH posts (zap-internal double-fire / clone step - a config bug)
  - class C: writes from TWO DIFFERENT actors/sources precede the two posts (two systems touching
             the same person - a different disease again, e.g. WF-1 + Make both writing)
  - class U: no changelog entry found near either post (unresolved - state it, don't guess)
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
HARVEST = os.path.join(OUT, "slack_duplicate_harvest.json")
LEAD_MAP = os.path.join(OUT, "lead_person_map.json")
PRIMARY_S = 120
NEAR_S = 24 * 3600


def load():
    rows = json.load(open(HARVEST, encoding="utf-8"))
    lead_map = json.load(open(LEAD_MAP, encoding="utf-8"))
    return rows, lead_map


def main():
    rows, lead_map = load()
    print(f"harvest rows: {len(rows)}")
    by_key = defaultdict(list)
    for r in rows:
        by_key[(r.get("lead_uuid"), r.get("template"))].append(r)

    primary, near, repeat = [], [], []
    for (uuid, tmpl), items in by_key.items():
        if len(items) < 2 or not uuid:
            continue
        items = sorted(items, key=lambda x: x["timestamp_unix"])
        for i in range(len(items) - 1):
            a, b = items[i], items[i + 1]
            gap = b["timestamp_unix"] - a["timestamp_unix"]
            pair = {"lead_uuid": uuid, "template": tmpl, "poster": a.get("poster"),
                   "lead_name": a.get("lead_name"), "campaign": a.get("campaign"),
                   "t1": a["timestamp_display"], "t2": b["timestamp_display"], "gap_s": gap,
                   "person_id": (lead_map.get(uuid) or {}).get("person_id")}
            if gap <= PRIMARY_S:
                primary.append(pair)
            elif gap <= NEAR_S:
                near.append(pair)
            else:
                repeat.append(pair)

    print(f"\nPRIMARY duplicates (<=120s): {len(primary)}")
    print(f"NEAR-window (2min-24h):      {len(near)}")
    print(f"REPEAT (>24h, diff-day):     {len(repeat)}")

    by_poster_tmpl = defaultdict(int)
    for p in primary:
        by_poster_tmpl[(p["poster"], p["template"])] += 1
    print("\nPRIMARY duplicates by poster+template:")
    for k, v in sorted(by_poster_tmpl.items(), key=lambda kv: -kv[1]):
        print(f"  {v:>4}  {k}")

    for name, dataset in (("duplicates_primary", primary), ("duplicates_near", near),
                          ("duplicates_repeat", repeat)):
        path = os.path.join(OUT, f"{name}.json")
        json.dump(dataset, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"wrote {path} ({len(dataset)} rows)")

    # also: how many DISTINCT leads have no person resolvable (map gap, not a duplicate-class issue)
    unresolved_person = [p for p in primary if not p.get("person_id")]
    print(f"\nprimary duplicates with no resolvable person_id: {len(unresolved_person)}")


if __name__ == "__main__":
    main()
