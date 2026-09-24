"""Complete backfill-300, per the owner's decision:
  1. Reassign the 300 just-created persons' owner_id from campaign-salesperson (Mario/Rune) to
     Melisa (16340280) - WF-2 uses Melisa uniformly for both persons and leads; two conventions in
     one backfill is exactly the "third convention" problem the owner flagged.
  2. Create the corresponding lead for each, following WF-2's OWN live lead-creation convention
     exactly: title `{campaign_id} - {campaign_name} - {name}`, channel=578, owner_id=16340280,
     label_ids=['cold'] (+'connected' if the row shows an accept - none of the 300 do, this is the
     email/Make side, no "accepted" concept), lead_opportunity_type field=480, lead_campaign
     field=campaign name (verbatim, matching WF-1/WF-2's own Campaign-field convention).

Handover-guard analysis (explicit, not skipped): these leads only ever carry 'cold', never
'responded' - neither "Responded handover to Melisa" nor "Responded already there" can fire (both
key on the responded label). "New lead owner" (fires on owner changed FROM Melisa) is Melisa's own
distribution mechanism firing exactly as designed once she reassigns these - not a defect to guard.
No suppression action is needed for this backfill.

WRITE_MODE=live required. Reads the MADE-person log lines + the campaign source file to rebuild
email -> person_id -> campaign, since the original backfill script didn't persist that mapping.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-forensics/1.0"
WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
MELISA = 16340280
CHANNEL = 578
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
OPP_VALUE = 480
LIVE_LOG = os.path.join(os.path.dirname(HERE), "AppData_placeholder")  # overridden below


def pd(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path, data=data, method=method,
                                       headers={"x-api-token": PDT, "User-Agent": UA,
                                                **({"Content-Type": "application/json"}
                                                   if data else {})})
            with urllib.request.urlopen(r, timeout=120) as x:
                return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return e.code, b
    return 0, None


def main(log_path):
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r}  ({'LIVE' if live else 'dry run'})")

    rows = [json.loads(l) for l in open(os.path.join(OUT, "ai4_missing_persons.jsonl"),
                                        encoding="utf-8")]
    by_email = {r["email"].lower(): r for r in rows}

    made = []
    for line in open(log_path, encoding="utf-8-sig"):
        m = re.match(r"\s*MADE\s+person\s+(\d+)\s+(\S+)", line.strip())
        if m:
            made.append((int(m.group(1)), m.group(2).lower()))
    print(f"parsed {len(made)} MADE lines from the live log")
    missing_row = [em for _, em in made if em not in by_email]
    if missing_row:
        sys.exit(f"ABORT: {len(missing_row)} emails from the log have no source row: "
                 f"{missing_row[:5]}")

    ok_owner = ok_lead = fail = 0
    for pid, email in made:
        row = by_email[email]
        try:
            if live:
                st, r = pd(f"/api/v2/persons/{pid}", "PATCH", {"owner_id": MELISA})
                if st >= 300:
                    raise RuntimeError(f"owner reassign failed: {st} {r}")
            ok_owner += 1

            title = f"{row['campaign_id']} - {row['campaign']} - {row.get('name') or email}"
            body = {"title": title, "person_id": pid, "owner_id": MELISA, "channel": CHANNEL,
                    "label_ids": [L_COLD], F_LEADCAMP: row["campaign"], F_OPP: OPP_VALUE}
            if live:
                st, r = pd("/v1/leads", "POST", body)
                if st >= 300:
                    raise RuntimeError(f"lead create failed: {st} {r}")
                lid = (r.get("data") or {}).get("id")
                print(f"  person {pid} owner->Melisa, lead {str(lid)[:8]} created  {email}")
            else:
                print(f"  WOULD reassign person {pid} owner->Melisa, WOULD create lead "
                      f"{title[:70]!r}  {email}")
            ok_lead += 1
        except Exception as e:                                  # noqa: BLE001
            fail += 1
            print(f"  FAILED {email}: {e}")

    print(f"\nowner reassigned: {ok_owner}/{len(made)}")
    print(f"leads created   : {ok_lead}/{len(made)}")
    print(f"failed          : {fail}")
    if not live:
        print("\nDRY RUN COMPLETE - nothing was written.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: backfill300_leads_and_owner_fix.py <path-to-bf300_live.log>")
    main(sys.argv[1])
