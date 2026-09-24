#!/usr/bin/env python3
"""Legacy Audit — Section C (READ-ONLY, local, no further API calls).
Counts person/lead duplicates from the name-match-instead-of-email-attachment class.

Checked the actual 84885/86/87 precedent first (task-logs/2026-08-10_independent-audit-...md,
p04_hygiene.py) rather than guess its shape: those three (+85506) are FOUR PERSON RECORDS SHARING
Person-ad46111a (pii-c61c7d08@example.invalid) - a flip-day test fixture, not organic legacy data, but it
defines the real defect signature to count: whatever created them matched/searched by NAME and
missed an existing record, so the SAME EMAIL ended up attached to more than one person. That's
SAME-EMAIL clustering, not same-name (an earlier pass here clustered by name and got swamped with
coincidental collisions like "michael"/"newsletter subscriber" - wrong shape, discarded).

Two distinct duplicate shapes counted separately, since they're different failure modes:
  1. SAME EMAIL, MULTIPLE PERSON RECORDS -> the 84885/86/87-class defect itself.
  2. SAME PERSON, MULTIPLE LEADS FOR THE SAME CAMPAIGN -> the lead-per-campaign convention
     (memory: wf1-w111-lead-per-campaign) being violated - a second lead created for a campaign
     that already had one, on the same person.

Known test fixtures are flagged and excluded from the headline count, not silently folded in.

Count only - no fixes, per explicit instruction that fixes are a separate decision.
"""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")

F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
KNOWN_TEST_FIXTURE_EMAILS = {"pii-c61c7d08@example.invalid"}  # flip-day test fixture, task-logs 2026-08-10


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


def main():
    persons = load_jsonl(os.path.join(EVID, "bulk_persons.jsonl"))
    leads = load_jsonl(os.path.join(EVID, "bulk_leads.jsonl"))
    print(f"input: {len(persons)} persons, {len(leads)} leads (bulk pull)")

    # --- 1. same-email, multiple-person-record clusters (the real 84885/86/87 shape) ---
    by_email = defaultdict(list)
    for p in persons:
        for e in (p.get("emails") or []):
            v = (e.get("value") or "").lower().strip()
            if v:
                by_email[v].append({"id": p["id"], "name": p.get("name"), "add_time": p.get("add_time")})
                break  # primary/first email only, avoid double-counting one person under 2 of their own addresses

    email_dup_clusters = []
    test_fixture_clusters = []
    for email, plist in by_email.items():
        ids = sorted({p["id"] for p in plist})
        if len(ids) < 2:
            continue
        cluster = {"email": email, "person_count": len(ids), "person_ids": ids,
                  "names": sorted({p["name"] for p in plist if p.get("name")}),
                  "add_times": sorted({p["add_time"] for p in plist if p.get("add_time")})}
        (test_fixture_clusters if email in KNOWN_TEST_FIXTURE_EMAILS else email_dup_clusters).append(cluster)

    email_dup_clusters.sort(key=lambda c: -c["person_count"])
    extra_person_records = sum(c["person_count"] - 1 for c in email_dup_clusters)
    extra_test_fixture_records = sum(c["person_count"] - 1 for c in test_fixture_clusters)

    # a second, cheap filter: internal domains / obvious test-name patterns, spotted by eye in the
    # top-count clusters (janeasystems.com, memurai.com staff test accounts; "test"/"newsletter
    # subscriber" placeholder names) - these are NOT organic legacy-system prospect duplicates and
    # blending them into the headline number would overstate the real defect. Flagged, not silently
    # dropped: reported as its own bucket.
    INTERNAL_DOMAINS = ("janeasystems.com", "memurai.com")
    TEST_NAME_MARKERS = ("test", "newsletter subscriber")

    def looks_internal_or_test(c):
        if c["email"].split("@")[-1].lower() in INTERNAL_DOMAINS:
            return True
        return any(any(m in (n or "").lower() for m in TEST_NAME_MARKERS) for n in c["names"])

    internal_test_clusters = [c for c in email_dup_clusters if looks_internal_or_test(c)]
    real_prospect_clusters = [c for c in email_dup_clusters if not looks_internal_or_test(c)]
    extra_internal_test_records = sum(c["person_count"] - 1 for c in internal_test_clusters)
    extra_real_prospect_records = sum(c["person_count"] - 1 for c in real_prospect_clusters)

    print(f"\n=== SECTION C.1 — same-email, multiple-person-record clusters (84885/86/87 class) ===")
    print(f"clusters found (excl. known flip-day test fixture): {len(email_dup_clusters)}")
    print(f"  of which internal/test-pattern (janeasystems.com/memurai.com staff, 'test'/'newsletter "
          f"subscriber' names): {len(internal_test_clusters)} clusters, {extra_internal_test_records} extra records")
    print(f"  REAL PROSPECT duplicates: {len(real_prospect_clusters)} clusters, "
          f"{extra_real_prospect_records} extra person records  <-- the honest headline number")
    print(f"known test-fixture clusters excluded separately: {len(test_fixture_clusters)} "
          f"({extra_test_fixture_records} extra records, e.g. 84885/86/87/85506)")
    print(f"\ntop 15 REAL PROSPECT clusters by person_count:")
    for c in real_prospect_clusters[:15]:
        print(f"  {c['email']:<40} persons={c['person_count']} names={c['names'][:3]} ids={c['person_ids'][:6]}")

    # --- 2. same person, multiple leads tagged to the SAME campaign (lead-per-campaign violation) ---
    person_campaign_leads = defaultdict(list)
    for l in leads:
        pid = l.get("person_id")
        if isinstance(pid, dict):
            pid = pid.get("value")
        camp = l.get(F_LEADCAMP)
        if pid and camp:
            person_campaign_leads[(pid, camp)].append(l["id"])

    lead_dup_pairs = [(k, v) for k, v in person_campaign_leads.items() if len(v) > 1]
    extra_lead_records = sum(len(v) - 1 for _, v in lead_dup_pairs)

    print(f"\n=== SECTION C.2 — same person, multiple leads for the same campaign ===")
    print(f"(person, campaign) pairs with >1 lead: {len(lead_dup_pairs)}")
    print(f"extra lead records beyond one-per-campaign: {extra_lead_records}")
    for (pid, camp), lids in sorted(lead_dup_pairs, key=lambda x: -len(x[1]))[:10]:
        print(f"  person {pid}  campaign={camp[:45]!r}  leads={len(lids)}  ids={lids[:4]}")

    out = {
        "email_dup_clusters_count_all": len(email_dup_clusters),
        "extra_person_records_all": extra_person_records,
        "real_prospect_clusters_count": len(real_prospect_clusters),
        "real_prospect_extra_records": extra_real_prospect_records,
        "real_prospect_clusters": real_prospect_clusters,
        "internal_test_clusters_count": len(internal_test_clusters),
        "internal_test_extra_records": extra_internal_test_records,
        "internal_test_clusters_sample": internal_test_clusters[:30],
        "flip_day_test_fixture_clusters_excluded": len(test_fixture_clusters),
        "flip_day_test_fixture_extra_records_excluded": extra_test_fixture_records,
        "flip_day_test_fixture_clusters": test_fixture_clusters,
        "lead_dup_pairs_count": len(lead_dup_pairs),
        "extra_lead_records": extra_lead_records,
        "lead_dup_pairs_sample": [{"person_id": pid, "campaign": camp, "lead_ids": v}
                                  for (pid, camp), v in lead_dup_pairs[:100]],
    }
    with open(os.path.join(EVID, "section_c_first_numbers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote evidence/section_c_first_numbers.json")


if __name__ == "__main__":
    main()
