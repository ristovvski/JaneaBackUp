#!/usr/bin/env python3
"""Build the full S4 retirement artifact from the recon fixtures already collected. Read-only --
just assembles what's already been queried into the row-level CSV/summary for §9f.2."""
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

recon = json.load(open(os.path.join(FIX, "s4_retirement_recon.json"), encoding="utf-8"))
clear686 = json.load(open(os.path.join(FIX, "s4_686_clear_candidates.json"), encoding="utf-8"))

pure_ids = recon["pure_s4_ids"]
by_source_ref = dict(recon["pure_s4_by_source_ref"])

print(f"Total rows to tombstone: {len(pure_ids)}")
print(f"By source_ref:")
for k, v in recon["pure_s4_by_source_ref"]:
    print(f"  {v:5d}  {k}")
print(f"\nPersons needing field-686 cleared: {clear686['clear_686_count']}")
for c in clear686.get("clear_686_sample", []):
    print(f"  pid={c['pipedrive_person_id']}  {c['full_name']}  ({c['identity_key']})")

# write a simple manifest -- just the ids + removed_reason, actual write script re-fetches full
# rows at fire time rather than trusting a snapshot to still be accurate.
manifest = {
    "ruling": "S4 RETIREMENT -- Melisa's ruling, Nik confirmed, 2026-08-26",
    "rationale": ("Our pool of potential customers is limited; real case -- Ai4 last-year "
                  "non-responders were re-contacted this year and some replied. Event contact "
                  "must not block re-approach; only a RESPONSE creates a relationship worth "
                  "protecting. -- Melisa, 2026-08-26"),
    "removed_reason_tag": "rule_change_2026-08-26_melisa",
    "total_tombstone_count": len(pure_ids),
    "field_686_clear_count": clear686["clear_686_count"],
    "field_686_clear_pids": clear686["clear_686_all_pids"],
    "tombstone_row_ids": pure_ids,
}
with open(os.path.join(FIX, "s4_retirement_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=1)
print(f"\nwrote fixtures/s4_retirement_manifest.json")
