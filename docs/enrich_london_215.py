"""
London Part 2: free enrichment of the 215 backfilled persons from Smartlead lead fields (provider
truth, no credits spent). Writes company, location, lh_linkedin_profile_url -- same Pipedrive
custom-field hashes WF-1 already uses (WF1_W1.0.1_build/WF1_KEYS.md):
  company            -> 5a282f55e910cceeb960969460b8409b4c10d623
  person_location    -> db219a0b68aa164d0aed1f7791687c5ae788b7ae
  li_url             -> 66f0af69bec838dc3f90bb3f16c7d6087d8dbb20

Guard: per-FIELD, not per-record -- only write a field that is currently empty on the live
Pipedrive person AND has a non-empty value in Smartlead. Never overwrite a populated field.
"""
import json
import os
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
F_COMPANY = "5a282f55e910cceeb960969460b8409b4c10d623"
F_LOCATION = "db219a0b68aa164d0aed1f7791687c5ae788b7ae"
F_LI_URL = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"


def load_env():
    with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
SL_KEY = os.environ["SMARTLEAD_API_KEY"]


def load_215():
    with open(os.path.join(HERE, "WF1_W1.0.1_build", "wf1-release-evidence",
                            "london_backfill_live_log.json"), encoding="utf-8") as f:
        return json.load(f)["rows"]


def plan_one(row):
    email = row["email"]
    pid = row["person_id"]

    r = requests.get("https://server.smartlead.ai/api/v1/leads",
                      params={"api_key": SL_KEY, "email": email}, timeout=20)
    sl = r.json() or {}
    if not sl or not sl.get("id"):
        return None, "no smartlead lead found"

    r = requests.get(f"https://api.pipedrive.com/v1/persons/{pid}",
                      params={"api_token": PD_TOKEN}, timeout=20)
    pd = (r.json() or {}).get("data") or {}
    if not pd:
        return None, "pipedrive person not found"

    updates = {}
    skipped_populated = []
    for field_key, sl_val in [(F_COMPANY, sl.get("company_name")),
                               (F_LOCATION, sl.get("location")),
                               (F_LI_URL, sl.get("linkedin_profile"))]:
        current = pd.get(field_key)
        if current:  # already populated -- never overwrite
            skipped_populated.append(field_key)
            continue
        if sl_val:
            updates[field_key] = sl_val

    return {"person_id": pid, "email": email, "updates": updates,
            "skipped_populated": skipped_populated}, None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dryrun"
    rows = load_215()
    print(f"215-set: {len(rows)} rows, mode={mode}")

    plans, errors = [], []
    for row in rows:
        plan, err = plan_one(row)
        if plan:
            plans.append(plan)
        else:
            errors.append({"person_id": row["person_id"], "email": row["email"], "error": err})
        time.sleep(0.2)

    writable = [p for p in plans if p["updates"]]
    print(f"\nplanned: {len(plans)}  writable (>=1 empty field to fill): {len(writable)}  "
          f"errors: {len(errors)}")
    for e in errors:
        print(f"  ERROR {e['person_id']} {e['email']}: {e['error']}")

    field_counts = {"company": 0, "location": 0, "li_url": 0}
    for p in writable:
        if F_COMPANY in p["updates"]:
            field_counts["company"] += 1
        if F_LOCATION in p["updates"]:
            field_counts["location"] += 1
        if F_LI_URL in p["updates"]:
            field_counts["li_url"] += 1
    print(f"fields being written: {field_counts}")

    out_dir = os.path.join(HERE, "audit-artifacts")
    with open(os.path.join(out_dir, "london_215_enrich_plan.json"), "w", encoding="utf-8") as f:
        json.dump({"writable": writable, "errors": errors}, f, indent=1)
    print(f"wrote {os.path.join(out_dir, 'london_215_enrich_plan.json')}")

    if mode == "dryrun":
        print("\ndry-run only, no writes.")
        return

    print(f"\nFIRING: writing {len(writable)} persons...")
    written, failed = [], []
    for p in writable:
        r = requests.put(f"https://api.pipedrive.com/v1/persons/{p['person_id']}",
                          params={"api_token": PD_TOKEN}, json=p["updates"], timeout=20)
        if r.status_code == 200 and (r.json() or {}).get("success"):
            written.append(p["person_id"])
        else:
            failed.append({"person_id": p["person_id"], "status": r.status_code, "body": r.text[:300]})
        time.sleep(0.2)

    print(f"written: {len(written)}  failed: {len(failed)}")
    with open(os.path.join(out_dir, "london_215_enrich_fire_result.json"), "w", encoding="utf-8") as f:
        json.dump({"written": written, "failed": failed}, f, indent=1)
    print(f"wrote {os.path.join(out_dir, 'london_215_enrich_fire_result.json')}")


if __name__ == "__main__":
    main()
