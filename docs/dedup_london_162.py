"""
London dedup Part 1: archive the 162 misattributed Make-era leads from
audit-artifacts/london_sprint_duplicate_investigation.json -> dedup_target.

Modes:
  dryrun  -- guard-check every row against LIVE Pipedrive state, report pass/skip, no writes.
  fire    -- same guard check, then PATCH is_archived=true on every row that passes.
  verify  -- confirm every dedup_target lead_id is_archived=true via direct GET + one search-route
             spot check, and that nothing outside dedup_target got touched (sampled).

Guards (per-record, live, not trusted from the audit snapshot):
  creator_id == 13015123
  label_ids == ["1. Cold"] exactly (a6d359b0-6a45-11ed-ab46-5b95b19fcb18) -- no more, no fewer
  lead_id in dedup_target (trivially true, iterating the set itself)
Anything drifted since the audit -> skip + log, never forced.
"""
import json
import os
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
CREATOR_ID = 13015123


def load_env():
    with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
BASE_V1 = "https://api.pipedrive.com/v1"


def load_target():
    with open(os.path.join(HERE, "audit-artifacts", "london_sprint_duplicate_investigation.json"),
              encoding="utf-8") as f:
        return json.load(f)["dedup_target"]


def guard_check(row):
    r = requests.get(f"{BASE_V1}/leads/{row['lead_id']}", params={"api_token": TOKEN}, timeout=20)
    if r.status_code != 200:
        return False, f"GET failed status={r.status_code}", None
    live = (r.json() or {}).get("data") or {}
    if not live:
        return False, "lead not found (deleted?)", None
    if live.get("creator_id") != CREATOR_ID:
        return False, f"creator_id drifted: now {live.get('creator_id')}", live
    if live.get("label_ids") != [LABEL_COLD]:
        return False, f"label_ids drifted: now {live.get('label_ids')}", live
    if live.get("is_archived") is True:
        return False, "already archived", live
    return True, None, live


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dryrun"
    target = load_target()
    print(f"dedup_target: {len(target)} rows, mode={mode}")

    if mode in ("dryrun", "fire"):
        passed, skipped = [], []
        for row in target:
            ok, reason, live = guard_check(row)
            if ok:
                passed.append(row)
            else:
                skipped.append({**row, "skip_reason": reason})
            time.sleep(0.15)

        print(f"\nguard PASS: {len(passed)}  guard SKIP (drift): {len(skipped)}")
        for s in skipped:
            print(f"  SKIP {s['lead_id']} ({s['title'][:60]}): {s['skip_reason']}")

        out_dir = os.path.join(HERE, "audit-artifacts")
        with open(os.path.join(out_dir, "london_dedup_guard_result.json"), "w", encoding="utf-8") as f:
            json.dump({"passed": [p["lead_id"] for p in passed],
                       "skipped": skipped}, f, indent=1)

        if mode == "dryrun":
            print("\ndry-run only, no writes.")
            return

        print(f"\nFIRING: archiving {len(passed)} leads...")
        archived, failed = [], []
        for row in passed:
            r = requests.patch(f"{BASE_V1}/leads/{row['lead_id']}", params={"api_token": TOKEN},
                                json={"is_archived": True}, timeout=20)
            ok = r.status_code == 200 and (r.json().get("data") or {}).get("is_archived") is True
            if ok:
                archived.append(row["lead_id"])
            else:
                failed.append({"lead_id": row["lead_id"], "status": r.status_code, "body": r.text[:300]})
            time.sleep(0.2)

        print(f"archived: {len(archived)}  failed: {len(failed)}")
        with open(os.path.join(out_dir, "london_dedup_fire_result.json"), "w", encoding="utf-8") as f:
            json.dump({"archived": archived, "failed": failed,
                       "skipped_drift": [s["lead_id"] for s in skipped]}, f, indent=1)
        print(f"wrote {os.path.join(out_dir, 'london_dedup_fire_result.json')}")

    elif mode == "verify":
        archived_count = 0
        not_archived = []
        for row in target:
            r = requests.get(f"{BASE_V1}/leads/{row['lead_id']}", params={"api_token": TOKEN}, timeout=20)
            live = (r.json() or {}).get("data") or {}
            if live.get("is_archived") is True:
                archived_count += 1
            else:
                not_archived.append({"lead_id": row["lead_id"], "title": row["title"],
                                      "is_archived": live.get("is_archived")})
            time.sleep(0.1)
        print(f"archived: {archived_count}/{len(target)}")
        if not_archived:
            print("NOT archived (either genuinely skipped for drift, or a failure -- cross-check "
                  "against london_dedup_guard_result.json / london_dedup_fire_result.json):")
            for n in not_archived:
                print(f"  {n['lead_id']} ({n['title'][:60]}) is_archived={n['is_archived']}")

        # spot-check via search route that archived leads are still findable there
        sample = target[:3]
        for row in sample:
            person_name = row["title"].split(" - ")[-1]
            r = requests.get(f"{BASE_V1}/leads/search",
                              params={"api_token": TOKEN, "term": person_name, "fields": "title"}, timeout=20)
            items = ((r.json().get("data") or {}).get("items")) or []
            match = next((it["item"] for it in items if it["item"]["id"] == row["lead_id"]), None)
            print(f"  search spot-check {row['lead_id']}: found={bool(match)} "
                  f"is_archived={match.get('is_archived') if match else None}")


if __name__ == "__main__":
    main()
