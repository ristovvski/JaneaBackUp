#!/usr/bin/env python3
"""Clean the real Company DNC CSV into a ready-to-fire import payload: lowercase, strip leading
www., dedupe (keep earliest Created At per domain), reject free-mail domains defensively (none
found in this batch, but the check runs regardless -- see CREATE_DNC_DOMAINS_TABLE.md)."""
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

FREE_MAIL = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "aol.com", "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "pm.me", "gmx.com", "gmx.net", "mail.com", "zoho.com",
    "yandex.com", "yandex.ru", "qq.com", "163.com", "126.com", "naver.com", "web.de",
    "inbox.com", "fastmail.com", "hey.com", "tutanota.com", "rocketmail.com",
}


def clean_domain(d):
    d = (d or "").strip().lower()
    if d.startswith("www."):
        d = d[4:]
    return d


def main():
    with open(os.path.join(HERE, "company_dnc_export.csv"), encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"raw rows: {len(rows)}")

    by_domain = {}
    for r in rows:
        d = clean_domain(r.get("Master Domain"))
        if not d:
            continue
        created = r.get("Created At", "")
        if d not in by_domain or created < by_domain[d]["Created At"]:
            by_domain[d] = {"Created At": created, "Updated At": r.get("Updated At", "")}

    rejected_free_mail = sorted(set(by_domain.keys()) & FREE_MAIL)
    for d in rejected_free_mail:
        print(f"REJECTED (free-mail domain): {d}")
        del by_domain[d]

    payload_rows = [
        {"domain": d, "added_at": meta["Created At"], "source": "clay_company_dnc_import",
         "reason": None, "status": "active"}
        for d, meta in sorted(by_domain.items())
    ]
    print(f"distinct domains after clean/dedupe/reject: {len(payload_rows)} (expected 1373)")

    out_path = os.path.join(HERE, "domains_import_payload.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"rows": payload_rows, "dry_run": True}, f, indent=1, ensure_ascii=False)
    print(f"wrote {out_path} — ready to fire once dnc_domains's real table id is known.")


if __name__ == "__main__":
    main()
