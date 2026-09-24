"""FULL-MATRIX Phase 1 - create the harness campaigns. Creates only; does NOT start.

One campaign per T-case so every reply lands in an unambiguous thread, each on its own Chrissy
inbox so the sends do not serialise behind min_time_btw_emails.

ORDERING CONSTRAINTS baked in below:
* T2 must send AFTER T1, because T2's whole point is "person already exists" - and the person only
  exists once Make has processed T1's send.
* T9 (DNC reply -> Smartlead unsubscribe) and T12 (unsubscribe click) GLOBALLY suppress
  pii-c61c7d08@example.invalid in Smartlead. Every send to that address must therefore happen before
  either is triggered, which is why all sends happen now and those two replies come last in Phase 2.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SL = "https://server.smartlead.ai/api/v1"
NIK = "pii-c61c7d08@example.invalid"
MANIFEST = Path(__file__).with_name("wf1-release-evidence") / "MATRIX_MANIFEST.json"

# T-case -> (campaign name, lead email, subject marker, purpose)
CASES = [
    ("T1",  "[Events Visiting] [WF2 Matrix T1] - Nik - Valids",  "pii-d9f65144@example.invalid",
     "brand-new person: person+org+lead born, trio, title convention, union [Cold]"),
    ("T2",  "[Events Visiting] [WF2 Matrix T2] - Nik - Valids",  "pii-d9f65144@example.invalid",
     "existing person, new campaign: second lead per-campaign, person campaign overwritten"),
    ("T11", "[Events Visiting] [WF2 Matrix T11] - Nik - Valids", "pii-233dbb9b@example.invalid",
     "bounce: note on lead, counter, no labels, no alert"),
    ("T5",  "[Events Visiting] [WF2 Matrix T5] - Nik - Valids",  NIK,
     "confident positive reply -> category + owner forward + alert (B26 first live proof); "
     "T7 reuses this thread for the second reply"),
    ("T6",  "[Events Visiting] [WF2 Matrix T6] - Nik - Valids",  NIK,
     "low-confidence reply -> Uncategorized, no SL category, REVIEW forward (B25 proof)"),
    ("T8",  "[Events Visiting] [WF2 Matrix T8] - Nik - Valids",  NIK,
     "manual label pre-seeded on the lead -> must survive the union (Silva-class)"),
    ("T9",  "[Events Visiting] [WF2 Matrix T9] - Nik - Valids",  NIK,
     "DNC reply -> DNC category, SL unsubscribe, PD DNC label, NO forward, NO alert"),
    ("T10", "[Events Visiting] [WF2 Matrix T10] - Nik - Valids", NIK,
     "no-lead path: PD records deleted before the reply -> person-side writes + warn"),
    ("T12", "[Events Visiting] [WF2 Matrix T12] - Nik - Valids", NIK,
     "unsubscribe click -> DNC procedure minus classification, silent"),
    ("T13", "[Lead Nurturing] [WF2 Matrix T13] - Nik - Valids", NIK,
     "nurture reply -> Slack-only note, ZERO CRM writes"),
]


def sl(path, method="GET", body=None, tries=3):
    key = os.environ["SMARTLEAD_API_KEY"]
    sep = "&" if "?" in path else "?"
    url = f"{SL}{path}{sep}api_key={key}"
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(tries):
        try:
            # Smartlead sits behind Cloudflare, which answers 403 "error code: 1010" to
            # urllib's default User-Agent. PowerShell worked only because it sends a normal one.
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) janea-matrix-harness/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:200]}"
            if e.code < 500:
                break
            time.sleep(2 * (i + 1))
        except Exception as e:                       # noqa: BLE001
            last = str(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{method} {path} failed -> {last}")


def main():
    senders = []
    p = Path(os.environ["TEMP"]) / "x"  # placeholder, real path below
    sfile = Path(r"C:\Users\User\AppData\Local\Temp\claude"
                 r"\C--Users-User-Desktop-----------\57dff599-8943-49f9-bca8-2051f2f62c47"
                 r"\scratchpad\matrix_senders.txt")
    for line in sfile.read_text(encoding="ascii").splitlines():
        if line.strip():
            sid, email = line.strip().split(",", 1)
            senders.append((int(sid), email))
    print(f"{len(senders)} Chrissy inboxes available\n")

    manifest = {"created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "recipient_primary": NIK, "cases": []}

    for idx, (tcase, name, lead_email, purpose) in enumerate(CASES):
        sid, sender = senders[idx % len(senders)]
        c = sl("/campaigns/create", "POST", {"name": name})
        cid = c["id"]
        sl(f"/campaigns/{cid}/email-accounts", "POST", {"email_account_ids": [sid]})
        added = sl(f"/campaigns/{cid}/leads", "POST", {"lead_list": [{
            "email": lead_email, "first_name": "Nik", "last_name": "Krivosheia",
            "company_name": "Janea Systems",
            "custom_fields": {"job_title": "Engineering Lead"}}]})
        subject = f"WF2 Matrix {tcase} - please reply"
        sl(f"/campaigns/{cid}/sequences", "POST", {"sequences": [{
            "seq_number": 1, "seq_delay_details": {"delay_in_days": 0},
            "subject": subject,
            "email_body": f"<div>Hi Nik,</div><div>Matrix case <b>{tcase}</b>. "
                          f"Reply with the exact text from the script.</div><div>Chrissy</div>"}]})
        sl(f"/campaigns/{cid}/schedule", "POST", {
            "timezone": "Etc/GMT", "days_of_the_week": [0, 1, 2, 3, 4, 5, 6],
            "start_hour": "00:00", "end_hour": "23:59",
            "min_time_btw_emails": 5, "max_new_leads_per_day": 10})
        row = {"case": tcase, "campaign_id": cid, "campaign_name": name,
               "lead_email": lead_email, "sender_id": sid, "sender": sender,
               "subject": subject, "purpose": purpose,
               "phase": 1 if tcase in ("T1", "T2", "T11") else 2,
               "upload": {k: added.get(k) for k in
                          ("upload_count", "invalid_email_count", "already_added_to_campaign")}}
        manifest["cases"].append(row)
        print(f"{tcase:<4} cid={cid}  sender={sender:<34} lead={lead_email}")
        print(f"     upload={row['upload']}")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmanifest -> {MANIFEST}")
    print("NOTHING STARTED YET - campaigns are staged only")


if __name__ == "__main__":
    main()
