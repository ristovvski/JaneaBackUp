"""Residual re-run: T7, T8, T10 harness campaigns (T12 is exercised synthetically).

Each case needs a precondition set AFTER the send and BEFORE the reply, which is why the last matrix
run could not prove them - all replies arrived at once. This run is pause-scripted.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SL = "https://server.smartlead.ai/api/v1"
NIK = "pii-c61c7d08@example.invalid"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) janea-matrix-harness/1.0"
MAN = Path(__file__).with_name("wf1-release-evidence") / "RESIDUAL_MANIFEST.json"

CASES = [
    ("T7", "[Events Visiting] [WF2 Residual T7] - Nik - Valids",
     "second reply after a FOUND lead -> CRM updated, NO second alert (first-reply gate)"),
    ("T8", "[Events Visiting] [WF2 Residual T8] - Nik - Valids",
     "manual label pre-seeded on the lead -> must survive the union (Silva-class)"),
    ("T10", "[Events Visiting] [WF2 Residual T10] - Nik - Valids",
     "Pipedrive records deleted before the reply -> no-lead path for the RIGHT reason"),
]


def sl(path, method="GET", body=None, tries=3):
    key = os.environ["SMARTLEAD_API_KEY"]
    sep = "&" if "?" in path else "?"
    url = f"{SL}{path}{sep}api_key={key}"
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:160]}"
            if e.code < 500:
                break
            time.sleep(2 * (i + 1))
        except Exception as e:                       # noqa: BLE001
            last = str(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{method} {path} -> {last}")


def main():
    sfile = Path(r"C:\Users\User\AppData\Local\Temp\claude"
                 r"\C--Users-User-Desktop-----------\57dff599-8943-49f9-bca8-2051f2f62c47"
                 r"\scratchpad\matrix_senders.txt")
    senders = []
    for line in sfile.read_text(encoding="ascii").splitlines():
        if line.strip():
            sid, email = line.strip().split(",", 1)
            senders.append((int(sid), email))

    man = {"created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cases": []}
    for idx, (case, name, purpose) in enumerate(CASES):
        sid, sender = senders[(idx + 3) % len(senders)]     # different inboxes from the last run
        cid = sl("/campaigns/create", "POST", {"name": name})["id"]
        sl(f"/campaigns/{cid}/email-accounts", "POST", {"email_account_ids": [sid]})
        sl(f"/campaigns/{cid}/leads", "POST", {"lead_list": [{
            "email": NIK, "first_name": "Nik", "last_name": "Krivosheia",
            "company_name": "Janea Systems",
            "custom_fields": {"job_title": "Engineering Lead"}}]})
        subject = f"WF2 Residual {case} - please reply"
        sl(f"/campaigns/{cid}/sequences", "POST", {"sequences": [{
            "seq_number": 1, "seq_delay_details": {"delay_in_days": 0}, "subject": subject,
            "email_body": f"<div>Hi Nik,</div><div>Residual case <b>{case}</b>. "
                          f"Reply with the exact text from the script.</div><div>Chrissy</div>"}]})
        sl(f"/campaigns/{cid}/schedule", "POST", {
            "timezone": "Etc/GMT", "days_of_the_week": [0, 1, 2, 3, 4, 5, 6],
            "start_hour": "00:00", "end_hour": "23:59",
            "min_time_btw_emails": 5, "max_new_leads_per_day": 10})
        man["cases"].append({"case": case, "campaign_id": cid, "campaign_name": name,
                             "lead_email": NIK, "sender": sender, "subject": subject,
                             "purpose": purpose})
        print(f"{case:<4} cid={cid}  sender={sender:<34} subject={subject!r}")

    MAN.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nmanifest -> {MAN}")
    print("ids:", [c["campaign_id"] for c in man["cases"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
