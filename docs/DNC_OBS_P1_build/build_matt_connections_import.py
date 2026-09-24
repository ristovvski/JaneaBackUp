"""
Matt Carothers LinkedIn connections -> DNC registry import (2026-08-19), same reason/entry_type/
owner_tag convention as the 2026-08-11 People-DNC seed (manual_offboard_eligible -> employee_connection,
owner_tag = source_ref, source = "onboarding_import:<name>") -- confirmed against dnc_seed_build.py.

Per Nik's explicit answers: include ALL rows (no company-based filtering -- matches precedent, the
original seed never filtered by company either), owner name = "Matt Carothers".

Row construction only, NO writes. Builds the payload list + the no-identity skip list, writes both
to fixtures/ for the pre-post review, same discipline as every other batch write this project.
"""
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = r"C:\Users\User\Downloads\Matt C LinkedIn connections.csv"
OWNER_NAME = "Matt Carothers"
SOURCE_TAG = "onboarding_import:" + OWNER_NAME

LI_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def canon_li(url):
    if not url:
        return None
    m = LI_RE.search(url)
    if not m:
        return None
    slug = m.group(1).split("?")[0].split("#")[0].rstrip("/")
    return f"https://www.linkedin.com/in/{slug.lower()}"


def main():
    with open(CSV_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    hdr_idx = next(i for i, l in enumerate(lines) if l.startswith("First Name"))
    reader = csv.DictReader(lines[hdr_idx:])
    rows = list(reader)
    print(f"total CSV rows: {len(rows)}")

    writable = []
    no_identity = []
    for r in rows:
        full_name = f"{(r.get('First Name') or '').strip()} {(r.get('Last Name') or '').strip()}".strip()
        li_url = canon_li((r.get("URL") or "").strip())
        email = (r.get("Email Address") or "").strip() or None
        company = (r.get("Company") or "").strip() or None
        position = (r.get("Position") or "").strip() or None

        if not li_url and not email:
            no_identity.append({"full_name": full_name, "company": company, "position": position})
            continue

        writable.append({
            "linkedin_url": li_url,
            "email": email,
            "full_name": full_name or None,
            "reason": "manual_offboard_eligible",
            "source": SOURCE_TAG,
            "source_ref": OWNER_NAME,
            "date_precision": "derived",
            "expiry_review_pending": False,
            "correlation_id": SOURCE_TAG + ":" + (li_url or email),
            # context-only, not sent to UpsertLedger -- for the pre-post review table
            "_company": company, "_position": position,
        })

    internal = [w for w in writable if (w["_company"] or "").lower() == "janea systems"]
    with_email = [w for w in writable if w["email"]]

    print(f"writable (has LinkedIn URL or email): {len(writable)}")
    print(f"no identity (skipped, logged): {len(no_identity)}")
    print(f"of writable, has an email too: {len(with_email)}")
    print(f"of writable, internal Janea Systems colleagues: {len(internal)} (INCLUDED per Nik's GO)")

    out_dir = os.path.join(HERE, "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "matt_carothers_connections_writable.json"), "w", encoding="utf-8") as f:
        json.dump(writable, f, indent=1)
    with open(os.path.join(out_dir, "matt_carothers_connections_no_identity.json"), "w", encoding="utf-8") as f:
        json.dump(no_identity, f, indent=1)
    print(f"\nwrote fixtures/matt_carothers_connections_writable.json ({len(writable)} rows)")
    print(f"wrote fixtures/matt_carothers_connections_no_identity.json ({len(no_identity)} rows)")


if __name__ == "__main__":
    main()
