#!/usr/bin/env python3
"""P1 REPAIR post-verify + handover damage report.

1. Compares pre-fire vs post-fire label snapshots: for every lead still resolvable, asserts DNC is
   gone and every OTHER label is byte-identical (same set) to before the strip. Any mismatch is
   printed, not silently swallowed.
2. Computes the handover-damage list: leads where "3. Responded" and our DNC label co-occurred at
   any point we have evidence for --
     (a) pre-fire snapshot shows BOTH present simultaneously (direct evidence), OR
     (b) other_labels_before (captured when we originally extracted this incident, i.e. the state
         right before we added DNC) already contained "3. Responded" -- meaning Responded was
         present at the moment we mislabeled them, so both were on the lead from that instant on.
   Cross-referenced against dnc_label_incident_final_live.json for names/person ids/reasons.

Usage: python zz_p1_verify_and_handover_damage.py <pre.json> <post.json>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DNC_LABEL_ID = "52a7c290-fc73-11f0-ad98-81d4703453f3"
INCIDENT_DATA_PATH = os.path.join(
    os.path.dirname(HERE), "SUPABASE_PROJECTION_build", "audit_out", "dnc_label_incident_final_live.json")


def main():
    if len(sys.argv) != 3:
        print("usage: python zz_p1_verify_and_handover_damage.py <pre.json> <post.json>")
        sys.exit(2)
    pre_path, post_path = sys.argv[1], sys.argv[2]

    with open(pre_path, encoding="utf-8") as f:
        pre = {r["lead_id"]: r for r in json.load(f)["leads"]}
    with open(post_path, encoding="utf-8") as f:
        post = {r["lead_id"]: r for r in json.load(f)["leads"]}
    with open(INCIDENT_DATA_PATH, encoding="utf-8") as f:
        incident = {r["lead_id"]: r for r in json.load(f)}

    assert set(pre) == set(post) == set(incident), "lead_id sets don't match across the three files"

    # ---------------------------------------------------------------- post-verify
    print("=" * 78)
    print("POST-VERIFY: DNC gone, every other label byte-identical")
    print("=" * 78)
    mismatches = []
    still_dnc = []
    gone_leads = []
    for lead_id, p in pre.items():
        q = post[lead_id]
        if not p["found"] and not q["found"]:
            gone_leads.append(lead_id)
            continue
        if p["found"] != q["found"]:
            mismatches.append((lead_id, "found-state changed", p["found"], q["found"]))
            continue
        if q.get("has_dnc"):
            still_dnc.append(lead_id)
        pre_other = set(p["label_ids"] or []) - {DNC_LABEL_ID}
        post_other = set(q["label_ids"] or []) - {DNC_LABEL_ID}
        if pre_other != post_other:
            mismatches.append((lead_id, "other labels changed", sorted(pre_other), sorted(post_other)))

    print(f"leads gone in both snapshots (expected 1, Jorge): {len(gone_leads)} -> {gone_leads}")
    print(f"leads STILL carrying DNC post-fire (expected 0): {len(still_dnc)} -> {still_dnc}")
    print(f"leads with any OTHER label mismatch pre vs post (expected 0): {len(mismatches)}")
    for m in mismatches:
        print(f"  MISMATCH {m}")
    verify_ok = not still_dnc and not mismatches and len(gone_leads) == 1
    print(f"\nPOST-VERIFY {'PASS' if verify_ok else 'FAIL'}")

    # ---------------------------------------------------------------- handover damage
    print("\n" + "=" * 78)
    print("HANDOVER DAMAGE: leads where 3.Responded co-occurred with our DNC label")
    print("=" * 78)
    damage = []
    for lead_id, p in pre.items():
        inc = incident[lead_id]
        direct = bool(p.get("has_dnc") and p.get("has_responded"))
        pre_existing = "3. Responded" in (inc.get("other_labels_before") or [])
        if direct or pre_existing:
            damage.append({
                "lead_id": lead_id,
                "pipedrive_person_id": inc["pipedrive_person_id"],
                "full_name": inc["full_name"],
                "reason": inc["reason"],
                "execution": inc["execution"],
                "evidence": ("both_present_pre_fire" if direct else "")
                            + ("+" if direct and pre_existing else "")
                            + ("responded_before_we_labeled" if pre_existing else ""),
            })
    damage.sort(key=lambda d: d["full_name"])
    print(f"total handover-damage leads: {len(damage)} of 600")
    for d in damage:
        print(f"  {d['full_name']:40s} person={d['pipedrive_person_id']:<10} lead={d['lead_id']} "
              f"reason={d['reason']:25s} evidence={d['evidence']}")

    out = {"verify_ok": verify_ok, "gone_leads": gone_leads, "still_dnc": still_dnc,
           "mismatches": mismatches, "handover_damage_count": len(damage), "handover_damage": damage}
    out_path = os.path.join(HERE, "audit-artifacts", "p1_repair_verify_and_handover_damage.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
