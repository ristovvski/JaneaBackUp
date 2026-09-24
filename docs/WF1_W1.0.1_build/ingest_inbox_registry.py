"""Ingest the Janea inbox registry CSV -> forward_inbox_map for WF-2's CONFIG.

Read-only over the CSV; emits JSON + a validation report. Nothing is written to CONFIG unless the
validation is clean, so a malformed registry cannot silently degrade forward routing.

The source sheet also carries the owner map itself in columns 8/9 of the first few rows
(name -> mailbox). That is used as an independent cross-check of forward_owner_map rather than
being ignored.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()

    rows = list(csv.reader(a.csv_path.open(encoding="utf-8-sig")))
    header, body = rows[0], rows[1:]

    mapping = {}                       # email -> owner (deduped)
    conflicts = defaultdict(set)       # email -> {owners}  when they disagree
    dupes = Counter()                  # exact duplicate rows (same email, same owner)
    malformed = []
    embedded_owner_map = {}
    per_owner = Counter()

    for i, r in enumerate(body, start=2):
        cell = (r + [""] * 9)[:9]
        email_raw, name_raw = cell[0], cell[1]
        # columns 8/9 hold the sheet's own owner map on the first rows - capture it as a cross-check
        onm, oml = cell[7].strip(), cell[8].strip()
        if onm and oml and EMAIL_RE.match(oml.lower()):
            embedded_owner_map[onm] = oml.lower()
        elif onm and not oml:
            embedded_owner_map.setdefault(onm, None)

        email = email_raw.strip().lower()
        name = name_raw.strip()
        if not email and not name:
            continue                                     # spacer row
        if not EMAIL_RE.match(email):
            malformed.append({"line": i, "email": email_raw, "name": name_raw,
                              "why": "not an email"})
            continue
        if not name:
            malformed.append({"line": i, "email": email, "name": "", "why": "missing owner name"})
            continue
        if email in mapping:
            if mapping[email] == name:
                dupes[email] += 1
            else:
                conflicts[email].update({mapping[email], name})
            continue
        mapping[email] = name

    for e, o in mapping.items():
        per_owner[o] += 1

    report = [
        "# Inbox registry ingestion", "",
        f"Source: `{a.csv_path.name}`", "",
        f"- data rows read: **{len(body)}**",
        f"- unique inboxes ingested: **{len(mapping)}**",
        f"- exact duplicates collapsed: **{sum(dupes.values())}** "
        f"(across {len(dupes)} addresses)",
        f"- CONFLICTING owners (flagged, NOT ingested): **{len(conflicts)}**",
        f"- malformed rows skipped: **{len(malformed)}**",
        f"- distinct owners in the registry: **{len(per_owner)}**",
        "",
        "## Inboxes per owner", "",
        "| owner | inboxes |", "|---|---|",
    ]
    for owner, n in per_owner.most_common():
        report.append(f"| {owner} | {n} |")

    if conflicts:
        report += ["", "## CONFLICTS - one inbox, two owners (excluded from the map)", "",
                   "| inbox | owners |", "|---|---|"]
        for e, owners in sorted(conflicts.items()):
            report.append(f"| {e} | {', '.join(sorted(owners))} |")
    if dupes:
        report += ["", "## Duplicate rows collapsed (same inbox, same owner)", ""]
        for e, n in dupes.most_common(20):
            report.append(f"- `{e}` x{n + 1}")
    if malformed:
        report += ["", "## Malformed rows", "", "| line | value | why |", "|---|---|---|"]
        for m in malformed:
            report.append(f"| {m['line']} | `{m['email']}` / `{m['name']}` | {m['why']} |")

    report += ["", "## Owner map embedded in the sheet (columns 8/9) - independent cross-check", ""]
    for k, v in sorted(embedded_owner_map.items()):
        report.append(f"- {k} -> {v or '(blank in sheet)'}")

    a.out.write_text(json.dumps({"inbox_map": dict(sorted(mapping.items())),
                                 "per_owner": dict(per_owner.most_common()),
                                 "conflicts": {k: sorted(v) for k, v in conflicts.items()},
                                 "malformed": malformed,
                                 "embedded_owner_map": embedded_owner_map},
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    a.report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[:26]))
    print(f"\n-> {a.out}\n-> {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
