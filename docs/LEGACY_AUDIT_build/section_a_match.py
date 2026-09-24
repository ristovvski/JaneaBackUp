#!/usr/bin/env python3
"""Legacy Audit — Section A matcher (READ-ONLY, local, no further API calls).
Matches every historical reply (from section_ab_raw_sweep.jsonl) against the bulk Pipedrive
pull (bulk_persons.jsonl + bulk_leads.jsonl) to find replies with NO CRM trace.

Tonight's pass uses LABEL evidence only (person exists + a lead of theirs carries the
"responded"-class label) - this is the cheap, already-bulk-pulled signal. Activity-level
corroboration (an actual reply-activity note) is a heavier per-record check not yet run at full
scale; flagged explicitly as a follow-up, not silently skipped.

Classification per unmatched reply:
  - no_person:              no Pipedrive person record exists for this email at all, ever
  - person_no_responded:    a person exists, but none of their leads carry the responded label
                             (the reply happened, contact record exists, but nothing marked it)
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")

L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
L_CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    sweep = load_jsonl(os.path.join(EVID, "section_ab_raw_sweep.jsonl"))
    persons = load_jsonl(os.path.join(EVID, "bulk_persons.jsonl"))
    leads = load_jsonl(os.path.join(EVID, "bulk_leads.jsonl"))
    print(f"input: {len(sweep)} campaigns swept, {len(persons)} persons, {len(leads)} leads (bulk pull)")

    email_to_person = {}
    for p in persons:
        for e in (p.get("emails") or []):
            v = (e.get("value") or "").lower().strip()
            if v:
                email_to_person.setdefault(v, []).append(p["id"])

    person_to_leads = {}
    for l in leads:
        pid = l.get("person_id")
        if isinstance(pid, dict):
            pid = pid.get("value")
        if pid:
            person_to_leads.setdefault(pid, []).append(l)

    print(f"email index: {len(email_to_person)} unique emails with a Pipedrive person")

    all_replies = []
    for c in sweep:
        if c.get("error"):
            continue
        for r in c.get("replies", []):
            all_replies.append({**r, "campaign_id": c["campaign_id"], "campaign_name": c["campaign_name"]})

    unique_replied_emails = {}
    for r in all_replies:
        unique_replied_emails.setdefault(r["email"], []).append(r)
    print(f"\ntotal reply records (all history, all campaigns): {len(all_replies)}")
    print(f"unique replied email addresses: {len(unique_replied_emails)}")

    no_person, person_no_responded, traced = [], [], []
    for email, reply_list in unique_replied_emails.items():
        pids = email_to_person.get(email)
        if not pids:
            no_person.append({"email": email, "replies": reply_list})
            continue
        has_responded = False
        for pid in pids:
            for lead in person_to_leads.get(pid, []):
                if L_RESPONDED in (lead.get("label_ids") or []):
                    has_responded = True
                    break
            if has_responded:
                break
        if has_responded:
            traced.append(email)
        else:
            person_no_responded.append({"email": email, "person_ids": pids, "replies": reply_list})

    print(f"\n=== SECTION A — FIRST NUMBERS (label-evidence pass) ===")
    print(f"  traced (person + responded label found):  {len(traced)}")
    print(f"  person_no_responded (person exists, NOT labeled responded): {len(person_no_responded)}")
    print(f"  no_person (no Pipedrive person at all):   {len(no_person)}")
    total_lost = len(person_no_responded) + len(no_person)
    print(f"  TOTAL WITH NO RESPONDED-LABEL TRACE: {total_lost} / {len(unique_replied_emails)} "
          f"({100*total_lost/len(unique_replied_emails):.1f}%)")

    # breakdown by campaign family (first bracket token or name prefix heuristic)
    from collections import Counter
    fam_counter_lost = Counter()
    fam_counter_total = Counter()
    campaign_name_by_id = {c["campaign_id"]: c["campaign_name"] for c in sweep}
    lost_emails = {x["email"] for x in no_person} | {x["email"] for x in person_no_responded}
    for email, reply_list in unique_replied_emails.items():
        # attribute to the first campaign this email replied in
        cname = reply_list[0].get("campaign_name") or campaign_name_by_id.get(reply_list[0].get("campaign_id"), "?")
        fam = cname.split(" - ")[0].split(" – ")[0].strip()
        fam_counter_total[fam] += 1
        if email in lost_emails:
            fam_counter_lost[fam] += 1

    print(f"\n=== by campaign family (lost / total replied) ===")
    for fam, total in fam_counter_total.most_common():
        lost = fam_counter_lost.get(fam, 0)
        print(f"  {fam[:55]:<55} {lost:>4} / {total:>4}  ({100*lost/total:.0f}%)")

    out = {
        "total_reply_records": len(all_replies),
        "unique_replied_emails": len(unique_replied_emails),
        "traced_count": len(traced),
        "person_no_responded_count": len(person_no_responded),
        "no_person_count": len(no_person),
        "total_lost": total_lost,
        "total_lost_pct": round(100 * total_lost / len(unique_replied_emails), 2) if unique_replied_emails else None,
        "by_family": {fam: {"lost": fam_counter_lost.get(fam, 0), "total": total}
                     for fam, total in fam_counter_total.items()},
        "no_person_sample": no_person[:50],
        "person_no_responded_sample": person_no_responded[:50],
        "caveat": "label-evidence pass only; activity-level (reply-note) corroboration not yet run "
                  "at full scale - a subset of 'person_no_responded' may still have an untagged "
                  "activity note as evidence, which would move them from lost to traced-but-unlabeled.",
    }
    with open(os.path.join(EVID, "section_a_first_numbers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote evidence/section_a_first_numbers.json")


if __name__ == "__main__":
    main()
