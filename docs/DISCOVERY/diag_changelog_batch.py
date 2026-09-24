#!/usr/bin/env python3
"""READ-ONLY batch diagnosis: for every ZapierBot tight-duplicate pair (<=120s) in the reporting
window, resolve lead->person, pull the person changelog, and count distinct Pipedrive write
"events" (grouped by identical timestamp = one PATCH call) landing in the 60s BEFORE the earlier
Slack post. Classifies each pair as ONE_WRITE_TWO_POSTS / TWO_WRITES_TWO_POSTS / NO_WRITE_FOUND.
"""
import json, os, time, requests
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.environ["PIPEDRIVE_API_TOKEN"]; B = "https://janeasystems.pipedrive.com/api/v1"
S = requests.Session()

pairs = json.load(open(os.path.join(HERE, "dup_ledger_output.json"), encoding="utf-8"))["tight_pairs"]

def get(path, params):
    for i in range(4):
        try:
            r = S.get(B + path, params={**params, "api_token": T}, timeout=30)
            if r.status_code == 429:
                time.sleep(3 * (i + 1)); continue
            return r.json()
        except Exception as e:
            if i == 3:
                return {"__err": str(e)[:200]}
            time.sleep(2)
    return {}

results = []
person_cache = {}
for i, p in enumerate(pairs):
    uuid = p["identity"]
    if uuid.count("-") != 4:
        continue
    lead = get(f"/leads/{uuid}", {})
    ld = (lead or {}).get("data") or {}
    person_id = ld.get("person_id")
    if not person_id:
        results.append({**p, "diagnosis": "LEAD_OR_PERSON_NOT_FOUND"})
        continue
    if person_id not in person_cache:
        cl = get(f"/persons/{person_id}/changelog", {"start": 0, "limit": 100})
        person_cache[person_id] = (cl or {}).get("data") or []
        time.sleep(0.15)
    rows = person_cache[person_id]

    ts_a = datetime.fromisoformat(p["ts_a"])
    window_start = ts_a - timedelta(seconds=60)
    window_end = ts_a + timedelta(seconds=5)
    hits = []
    for r in rows:
        try:
            t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if window_start <= t <= window_end:
            hits.append({"time": r["time"], "field_key": r["field_key"], "actor_user_id": r.get("actor_user_id"),
                         "change_source": r.get("change_source"), "ua": r.get("change_source_user_agent")})
    distinct_write_timestamps = sorted({h["time"] for h in hits})
    if not hits:
        diag = "NO_WRITE_FOUND_IN_60S_PRIOR"
    elif len(distinct_write_timestamps) == 1:
        diag = "ONE_WRITE_TWO_POSTS"
    else:
        diag = "TWO_OR_MORE_WRITES"
    results.append({**p, "person_id": person_id, "diagnosis": diag,
                     "write_timestamps": distinct_write_timestamps,
                     "actors": sorted({(h["actor_user_id"], h["change_source"]) for h in hits}),
                     "hit_count": len(hits)})
    print(f"[{i+1}/{len(pairs)}] {p['lead_name'][:50]:50s} person={person_id} -> {diag} "
          f"(writes={len(distinct_write_timestamps)}, actors={results[-1]['actors']})")

with open(os.path.join(HERE, "changelog_diagnosis.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)

from collections import Counter
print("\n=== SUMMARY ===")
print(Counter(r["diagnosis"] for r in results))
print("wrote changelog_diagnosis.json")
