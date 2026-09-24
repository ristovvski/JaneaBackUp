"""
Phase B of the People-DNC identity resolution: pure in-memory resolve against the local
Pipedrive person index built by dnc_pull_pipedrive_persons.py. Zero API calls, zero writes.

Output: a resolution report (matched / creatable / needs-review counts) only.
Person creation policy is a SEPARATE decision, not made by this script.

Usage: python dnc_resolve_people_dnc.py
Requires: fixtures/pipedrive_persons_index.json (from Phase A) and
          fixtures/people_dnc_seed_preview.json (from the dry-run merge)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(HERE, "fixtures", "pipedrive_persons_index.json")
SEED_FILE = os.path.join(HERE, "fixtures", "people_dnc_seed_preview.json")
OUT_FILE = os.path.join(HERE, "fixtures", "people_dnc_resolution_report.json")


def main():
    if not os.path.exists(INDEX_FILE):
        print(f"MISSING: {INDEX_FILE} -- run dnc_pull_pipedrive_persons.py (full, not --sanity) first.")
        sys.exit(1)

    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)

    by_li = index["by_li_url_canon"]
    by_li_deleted = index["by_li_url_canon_deleted"]

    results = {"matched": [], "matched_deleted_only": [], "creatable": []}
    for row in seed["registry_rows"]:
        identity = row["identity_key"]
        live_hits = by_li.get(identity, [])
        deleted_hits = by_li_deleted.get(identity, [])

        if live_hits:
            results["matched"].append({
                "identity_key": identity, "person_ids": live_hits,
                "ambiguous": len(live_hits) > 1, "reason": row["reason"],
            })
        elif deleted_hits:
            # identity only matches a soft-deleted person -- do NOT treat as a live match.
            # Has enough identity to create fresh, but flag that a deleted record exists under this identity.
            results["matched_deleted_only"].append({
                "identity_key": identity, "deleted_person_ids": deleted_hits, "reason": row["reason"],
            })
        else:
            results["creatable"].append({
                "identity_key": identity, "reason": row["reason"], "source_ref": row["source_ref"],
            })

    summary = {
        "total_seed_rows": len(seed["registry_rows"]),
        "matched_live_person": len(results["matched"]),
        "matched_ambiguous_multi_person": sum(1 for r in results["matched"] if r["ambiguous"]),
        "matched_only_a_deleted_person": len(results["matched_deleted_only"]),
        "creatable_no_existing_person": len(results["creatable"]),
        "creatable_by_reason": {},
    }
    for r in results["creatable"]:
        summary["creatable_by_reason"][r["reason"]] = summary["creatable_by_reason"].get(r["reason"], 0) + 1

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nFull resolution detail written to {OUT_FILE}")
    print("\nNO Pipedrive writes were made. NO persons were created. Creation policy is a separate decision.")


if __name__ == "__main__":
    main()
