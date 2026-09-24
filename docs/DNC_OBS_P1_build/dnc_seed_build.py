"""
SEED WRITE Pass 1 -- row construction only, NO writes. Builds the exact 23 registry-row shapes
for dnc_registry_dev (23,838 People-DNC + paul.gilford) and 7-col rows for dnc_domain_block_dev
(company domains), per owner's explicit 2026-08-11 GO + creation policy:

1. NO Pipedrive person creation for creatable rows. pipedrive_person_id=null,
   projections_state = {pipedrive: skipped:no_person, smartlead: pending if email else
   skipped:no_email, heyreach: pending}.
2. Clean-matched (single live person): full row with person_id, projections_state all "pending"
   (projections don't fire this pass regardless -- registry-only).
3. Ambiguous (>1 live person matched): reason intact, pipedrive_person_id=null,
   projections_state.pipedrive = "held:ambiguous" (smartlead/heyreach follow the same
   email-presence rule as creatable -- the ambiguity is only about WHICH Pipedrive person, it
   does not block the identity-key-based DNC hold). Candidate person_ids go to a separate review
   file, NOT a table column (no such column exists).
5. Projections themselves never fire in this pass -- only "pending"/"skipped:*"/"held:*" states,
   never "done".

Uses merge_v1.js / reason_v1.js semantics directly (re-implemented in Python here since this is a
bulk offline construction, not a live UpsertLedger call) -- TTL=6mo, computeExpiry, reasonExpiryOverride,
REASON_TO_ENTRY_TYPE, exactly as embedded in the live workflow, so seeded rows are indistinguishable
from what a real UpsertLedger insert would have produced.
"""
import csv, json, os, re
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

SEED_PREVIEW = os.path.join(FIX, "people_dnc_seed_preview.json")
PENDING_MANUAL = os.path.join(FIX, "pending_manual_seed_rows.json")
RESOLUTION_REPORT = os.path.join(FIX, "people_dnc_resolution_report.json")
PERSONS_CACHE = os.path.join(FIX, "pipedrive_persons_cache.jsonl")
PERSONS_INDEX = os.path.join(FIX, "pipedrive_persons_index.json")
COMPANY_CSV = r"C:\Users\User\Downloads\Company-DNC-Copy-of-Default-view-export-1786102974783.csv"

OUT_PEOPLE = os.path.join(FIX, "seed_write_payload_people.json")
OUT_DOMAINS = os.path.join(FIX, "seed_write_payload_domains.json")
OUT_AMBIGUOUS_REVIEW = os.path.join(HERE, "AMBIGUOUS_PERSON_REVIEW_2026-08-11.json")

TTL_MONTHS = 6
NOW_ISO = "2026-08-11T00:00:00.000Z"  # seed-run timestamp, stamped once for the whole batch

REASON_TO_ENTRY_TYPE = {
    "client": "explicit_opt_out",
    "unsubscribe": "explicit_opt_out",
    "reply_dnc": "negative_reply",
    "manual_offboard_eligible": "employee_connection",
    "manual_sheet": "manual",
    "offboard": "manual",
}
PERMANENT_ENTRY_TYPES = {"explicit_opt_out", "employee_connection"}


def strip_annotation(raw_date):
    """'2026-08-07(import date)' -> '2026-08-07T00:00:00.000Z'; already-clean dates pass through."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw_date.strip())
    if not m:
        raise ValueError(f"unparseable date: {raw_date!r}")
    return m.group(1) + "T00:00:00.000Z"


def add_months_iso(iso, months):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    d2 = d + relativedelta(months=months)
    return d2.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def compute_expiry(entry_type, added_at_iso):
    if entry_type in PERMANENT_ENTRY_TYPES:
        return None
    if entry_type in ("replied", "negative_reply"):
        return add_months_iso(added_at_iso, TTL_MONTHS)
    return None  # manual: permanent unless an explicit expires_at is supplied (none here)


def reason_expiry_override(reason, date_precision, computed_expiry):
    if reason == "reply_dnc" and date_precision == "unknown":
        return None
    return computed_expiry


def canon_li(slug_or_none):
    if not slug_or_none:
        return None
    return f"https://www.linkedin.com/in/{slug_or_none}"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_person_lookup():
    by_id = {}
    with open(PERSONS_CACHE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            pid = p.get("id")
            emails = p.get("emails") or p.get("email") or []
            primary_email = None
            for e in emails:
                addr = e.get("value") if isinstance(e, dict) else e
                is_primary = e.get("primary") if isinstance(e, dict) else False
                if addr and (is_primary or primary_email is None):
                    primary_email = addr.strip().lower()
                    if is_primary:
                        break
            by_id[pid] = {"name": p.get("name") or None, "email": primary_email}
    return by_id


def main():
    seed = load_json(SEED_PREVIEW)
    pending_manual = load_json(PENDING_MANUAL)
    resolution = load_json(RESOLUTION_REPORT)
    index = load_json(PERSONS_INDEX)
    person_lookup = build_person_lookup()

    by_li = index["by_li_url_canon"]
    by_li_deleted = index["by_li_url_canon_deleted"]
    by_email = index["by_email_lc"]

    # index resolution results by identity_key for O(1) lookup while walking the seed rows
    res_matched = {r["identity_key"]: r for r in resolution["results"]["matched"]}

    counts = {"matched_clean": 0, "matched_ambiguous": 0, "creatable": 0}
    ambiguous_review_rows = []
    people_rows = []

    for row in seed["registry_rows"]:
        identity = row["identity_key"]
        reason = row["reason"]
        entry_type = REASON_TO_ENTRY_TYPE[reason]
        added_at = strip_annotation(row["added_at"])
        date_precision = row["date_precision"]
        expiry = reason_expiry_override(reason, date_precision, compute_expiry(entry_type, added_at))

        m = res_matched.get(identity)
        live_hits = by_li.get(identity, [])
        is_ambiguous = bool(m and m["ambiguous"])

        if live_hits and not is_ambiguous:
            pid = live_hits[0]
            counts["matched_clean"] += 1
            person = person_lookup.get(pid, {})
            pipedrive_person_id = pid
            email_lc = person.get("email")
            full_name = person.get("name")
            proj = {
                "pipedrive": "pending", "smartlead": "pending" if email_lc else "skipped:no_email",
                "heyreach": "pending",
            }
        elif is_ambiguous:
            counts["matched_ambiguous"] += 1
            pipedrive_person_id = None
            email_lc = None
            full_name = None
            proj = {"pipedrive": "held:ambiguous", "smartlead": "skipped:no_email", "heyreach": "pending"}
            ambiguous_review_rows.append({
                "identity_key": identity, "reason": reason,
                "candidate_person_ids": live_hits,
                "candidate_names": [person_lookup.get(pid, {}).get("name") for pid in live_hits],
            })
        else:
            counts["creatable"] += 1
            pipedrive_person_id = None
            email_lc = None
            full_name = None
            proj = {"pipedrive": "skipped:no_person", "smartlead": "skipped:no_email", "heyreach": "pending"}

        owner_tag = row["source_ref"] if reason == "manual_offboard_eligible" else None
        source_tag = "onboarding_import:" + (row["source_ref"] or row["source"] or "people_dnc_csv")

        people_rows.append({
            "identity_key": identity,
            "linkedin_url_norm": canon_li(identity),
            "email_lc": email_lc,
            "full_name": full_name,
            "pipedrive_person_id": pipedrive_person_id,
            "entry_type": entry_type,
            "source": source_tag,
            "owner_tag": owner_tag,
            "reply_category": None,
            "status": "active",
            "added_at": added_at,
            "expires_at": expiry,
            "removed_at": None,
            "removed_reason": None,
            "correlation_id": "seed_2026-08-11:people_dnc_pass1",
            "norm_v": "v1",
            "reason": reason,
            "source_ref": row["source_ref"],
            "also_flagged": json.dumps(row["also_flagged"]),
            "date_precision": date_precision,
            "offboard_removable": row["offboard_removable"],
            "expiry_review_pending": False,
            "projections_state": json.dumps(proj),
        })

    # --- paul.gilford (email identity, single row, same resolve-by-email + no-creation policy) ---
    pg = pending_manual["rows"][0]
    pg_email = pg["email_lc"]
    pg_hits = by_email.get(pg_email, [])
    pg_ambiguous = len(pg_hits) > 1
    if pg_hits and not pg_ambiguous:
        pid = pg_hits[0]
        person = person_lookup.get(pid, {})
        pg_pipedrive_id = pid
        pg_full_name = person.get("name")
        pg_proj = {"pipedrive": "pending", "smartlead": "pending", "heyreach": "pending"}
        counts["matched_clean"] += 1
    elif pg_ambiguous:
        pg_pipedrive_id = None
        pg_full_name = None
        pg_proj = {"pipedrive": "held:ambiguous", "smartlead": "pending", "heyreach": "pending"}
        counts["matched_ambiguous"] += 1
        ambiguous_review_rows.append({
            "identity_key": pg_email, "reason": pg["reason"],
            "candidate_person_ids": pg_hits,
            "candidate_names": [person_lookup.get(pid, {}).get("name") for pid in pg_hits],
        })
    else:
        pg_pipedrive_id = None
        pg_full_name = None
        pg_proj = {"pipedrive": "skipped:no_person", "smartlead": "pending", "heyreach": "pending"}
        counts["creatable"] += 1

    pg_added_at = strip_annotation(pg["added_at"])
    pg_entry_type = pg["entry_type"]
    assert pg_entry_type == REASON_TO_ENTRY_TYPE[pg["reason"]], "paul.gilford entry_type mismatch vs mapping"
    pg_expiry = reason_expiry_override(pg["reason"], pg["date_precision"],
                                        compute_expiry(pg_entry_type, pg_added_at))

    people_rows.append({
        "identity_key": pg_email,
        "linkedin_url_norm": None,
        "email_lc": pg_email,
        "full_name": pg_full_name,
        "pipedrive_person_id": pg_pipedrive_id,
        "entry_type": pg_entry_type,
        "source": "smartlead_category",
        "owner_tag": None,
        "reply_category": pg["smartlead_category"],
        "status": "active",
        "added_at": pg_added_at,
        "expires_at": pg_expiry,
        "removed_at": None,
        "removed_reason": None,
        "correlation_id": "seed_2026-08-11:paul_gilford_manual",
        "norm_v": "v1",
        "reason": pg["reason"],
        "source_ref": pg["source_ref"],
        "also_flagged": json.dumps([]),
        "date_precision": pg["date_precision"],
        "offboard_removable": False,
        "expiry_review_pending": pg["expiry_review_pending"],
        "projections_state": json.dumps(pg_proj),
    })

    with open(OUT_PEOPLE, "w", encoding="utf-8") as f:
        json.dump(people_rows, f)
    with open(OUT_AMBIGUOUS_REVIEW, "w", encoding="utf-8") as f:
        json.dump({
            "_note": "64+ rows where an identity resolved to MORE THAN ONE live Pipedrive person. "
                     "Registry hold is already in effect (identity-key match covers all candidates) "
                     "-- this file is only for the lazy human decision of which person is canonical, "
                     "not a seed blocker.",
            "count": len(ambiguous_review_rows),
            "rows": ambiguous_review_rows,
        }, f, indent=2)

    print("=== People-DNC + paul.gilford row construction ===")
    print(f"total rows built: {len(people_rows)} (expect 23839)")
    print(json.dumps(counts, indent=2))
    print(f"ambiguous review rows written: {len(ambiguous_review_rows)} -> {OUT_AMBIGUOUS_REVIEW}")

    # --- company domains ---
    with open(COMPANY_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        csv_rows = list(r)
    raw_domains = [row[0].strip().lower() for row in csv_rows if row and row[0].strip()]
    seen = set()
    domain_rows = []
    dup_count = 0
    for d in raw_domains:
        if d in seen:
            dup_count += 1
            continue
        seen.add(d)
        domain_rows.append({
            "domain": d,
            "source": "company_dnc_sheet:legacy_import",
            "status": "active",
            "added_at": NOW_ISO,
            "removed_at": None,
            "removed_reason": None,
            "correlation_id": "seed_2026-08-11:company_domains_pass1",
        })

    with open(OUT_DOMAINS, "w", encoding="utf-8") as f:
        json.dump(domain_rows, f)

    print("\n=== Company-domains row construction ===")
    print(f"raw rows in CSV: {len(raw_domains)}, deduped: {len(domain_rows)}, in-file duplicates dropped: {dup_count}")
    print(f"wrote {OUT_DOMAINS}")


if __name__ == "__main__":
    main()
