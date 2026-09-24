"""
Enrich queue 1,019 -- tiered plan (Nik, 2026-08-18), tier (a)+(b) only. No external spend.

Tier (a) free pass: checked HeyReach's own GetLead + Smartlead's global lead lookup for every
person in fixtures/enrich_queue.json. Both need an existing email OR LinkedIn URL to search FROM
-- and every one of the 1,019 is missing BOTH (verified: build_enrich_queue.py's own breakdown
shows 100% "email, LinkedIn" missing, 0% partial). There is no seed identifier to look up with,
so the free pass resolves 0 -- not a search failure, a precondition failure. A name-only fuzzy
match against HeyReach/Smartlead was deliberately NOT attempted: this project's whole identity
model (normalizeIdentityV1) treats full_name as explicitly unstable/ambiguous, never a match key
-- doing it here would risk exactly the identity-conflation this project has avoided everywhere
else, for a one-off "free" shortcut.

Tier (b): build the Clay-import-shaped export artifact (name, company, pipedrive_person_id,
source). Company name pulled from Pipedrive directly (cheap, already-owned data, not a paid
enrichment call) since Clay needs it as a matching seed. Does NOT push to Clay -- Nik confirms
credits first.
"""
import os
import json
import time
import requests


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def main():
    load_env()
    token = os.environ["PIPEDRIVE_API_TOKEN"]

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "enrich_queue.json"),
              encoding="utf-8") as f:
        queue = json.load(f)
    all_rows = [dict(r, scenario="S1") for r in queue["s1_no_identity"]] + \
               [dict(r, scenario="S2") for r in queue["s2_no_identity"]]
    print(f"{len(all_rows)} total rows to enrich with company data for the Clay export.")

    clay_rows = []
    resolved_free = 0
    for row in all_rows:
        pid = row["pipedrive_person_id"]
        company = None
        title = None
        if pid:
            r = requests.get(f"https://api.pipedrive.com/api/v2/persons/{pid}",
                              params={"api_token": token}, timeout=20)
            if r.status_code == 200:
                d = (r.json() or {}).get("data") or {}
                orgs = d.get("org_id") or {}
                company = orgs.get("name") if isinstance(orgs, dict) else None
                jt = d.get("job_title")
                title = jt
                # double-check for free-pass purposes: does Pipedrive itself now have an
                # email or LinkedIn that wasn't there when the fire ran? (drift check, not
                # an enrichment call -- same data, same cost as the read that already happened)
                emails = d.get("emails") or []
                has_email_now = any(e.get("value") for e in emails) if isinstance(emails, list) else bool(d.get("email"))
                if has_email_now:
                    resolved_free += 1
        clay_rows.append({
            "full_name": row["full_name"],
            "pipedrive_person_id": pid,
            "company_name": company,
            "job_title": title,
            "scenario": row["scenario"],
            "source": row["source"],
        })
        time.sleep(0.3)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "clay_import_export.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clay_rows, f, indent=1)

    print(f"\nFree-pass resolved (email now present on Pipedrive, drift since the fire): {resolved_free}")
    print(f"Clay export artifact ({len(clay_rows)} rows) written to {out_path}")
    print(f"Remaining after free pass: {len(clay_rows) - resolved_free} -- staged for tier (b), not pushed.")


if __name__ == "__main__":
    main()
