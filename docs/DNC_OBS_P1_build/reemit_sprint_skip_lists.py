"""
Read-only re-emit of the S4 sales-sprint skip lists for campaigns 3565651 / 3565502, after the
"undefined x48" bug (Nik, 2026-08-14): the fired data itself was never wrong -- Has Identity? only
ever read linkedin_url/email, both correctly derived before the bug -- only the Slack skip-report
TEXT rendered "undefined" for STOPPED-status leads whose lead.* fields Smartlead had wiped to null,
because external_id (the fallback) was never actually propagated onto the upsert-input object.

This script re-derives the same skip list directly from Smartlead (no re-fire, no registry write)
using the now-fixed fallback logic (lead.id || campaign_lead_map_id), so it's safe to run any time.
"""
import os
import requests

CAMPAIGNS = [(3565651, "[Sales Sprint] Sales Sprint 2026 - London - Catch-alls", 1962),
             (3565502, "[Sales Sprint] Sales Sprint 2026 - London - Valids", 3145)]


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
    key = os.environ["SMARTLEAD_API_KEY"]
    ua = {"User-Agent": "Mozilla/5.0 janea-recon/1.0"}
    for cid, name, total in CAMPAIGNS:
        print(f"\n=== {name} (id {cid}) ===")
        offset = 0
        no_identity = []
        while offset < total:
            r = requests.get(f"https://server.smartlead.ai/api/v1/campaigns/{cid}/leads",
                              params={"api_key": key, "offset": offset, "limit": 100}, headers=ua, timeout=30)
            rows = r.json().get("data", [])
            if not rows:
                break
            for row in rows:
                l = row.get("lead") or {}
                email = l.get("email")
                li = l.get("linkedin_profile")
                if not email and not li:
                    full_name = " ".join(filter(None, [l.get("first_name"), l.get("last_name")])) or None
                    external_id = l.get("id") or row.get("campaign_lead_map_id")
                    no_identity.append((full_name, external_id, row.get("status")))
            offset += 100
        print(f"{len(no_identity)} skipped, no email/LinkedIn -- manual enrich needed:")
        for full_name, external_id, status in no_identity:
            if full_name:
                print(f"  - {full_name}")
            elif external_id:
                print(f"  - (no name/email/LinkedIn -- Smartlead campaign_lead_map_id {external_id}, "
                      f"lead status {status})")
            else:
                print("  - (no identifying info at all)")


if __name__ == "__main__":
    main()
