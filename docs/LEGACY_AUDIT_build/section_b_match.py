#!/usr/bin/env python3
"""Legacy Audit — Section B (READ-ONLY, local, no further API calls).
Contacted-vs-created per campaign, reusing section_ab_raw_sweep.jsonl's contacted_emails and the
same bulk Pipedrive email index built for Section A - one walk, both numbers, per Nik's directive.

"Created" = a Pipedrive person exists for the contacted email, full stop (existence, not
attribution-correctness - a person created under the wrong campaign still counts as "created" here;
campaign-attribution correctness is a separate question from "did the legacy system even make a
CRM record at all").
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


def main():
    sweep = load_jsonl(os.path.join(EVID, "section_ab_raw_sweep.jsonl"))
    persons = load_jsonl(os.path.join(EVID, "bulk_persons.jsonl"))
    print(f"input: {len(sweep)} campaigns, {len(persons)} persons (bulk pull)")

    email_set = set()
    for p in persons:
        for e in (p.get("emails") or []):
            v = (e.get("value") or "").lower().strip()
            if v:
                email_set.add(v)
    print(f"email index: {len(email_set)} unique emails with a Pipedrive person\n")

    per_campaign = []
    global_contacted = set()
    global_missing = set()
    for c in sweep:
        if c.get("error"):
            continue
        contacted = set(c.get("contacted_emails") or [])
        missing = contacted - email_set
        global_contacted |= contacted
        global_missing |= missing
        per_campaign.append({
            "campaign_id": c["campaign_id"], "campaign_name": c["campaign_name"],
            "created_at": c.get("created_at"), "status": c.get("status"),
            "contacted": len(contacted), "created": len(contacted) - len(missing),
            "missing": len(missing),
            "missing_pct": round(100 * len(missing) / len(contacted), 1) if contacted else None,
        })

    per_campaign.sort(key=lambda r: -r["missing"])
    print(f"=== SECTION B — FIRST NUMBERS (contacted-vs-created, per campaign) ===")
    print(f"global unique contacted (all campaigns, deduped): {len(global_contacted)}")
    print(f"global unique missing (no Pipedrive person at all): {len(global_missing)} "
          f"({100*len(global_missing)/len(global_contacted):.1f}%)")

    print(f"\ntop 20 campaigns by absolute missing count:")
    for r in per_campaign[:20]:
        print(f"  {r['campaign_id']} {r['campaign_name'][:48]:<48} "
              f"contacted={r['contacted']:>5} created={r['created']:>5} missing={r['missing']:>5} "
              f"({r['missing_pct']}%)  created_at={r['created_at'][:10] if r['created_at'] else '?'}")

    out = {"global_contacted": len(global_contacted), "global_missing": len(global_missing),
          "global_missing_pct": round(100*len(global_missing)/len(global_contacted), 2) if global_contacted else None,
          "per_campaign": per_campaign}
    with open(os.path.join(EVID, "section_b_first_numbers.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote evidence/section_b_first_numbers.json")


if __name__ == "__main__":
    main()
