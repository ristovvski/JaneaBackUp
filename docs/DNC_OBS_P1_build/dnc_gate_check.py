#!/usr/bin/env python3
"""
Pre-add DNC gate -- tiny wrapper. Reads a lead list (CSV or JSON), sends it to the gate webhook,
prints the CLEAN/BLOCKED/UNRESOLVABLE split, and saves the full annotated result next to your
input file. No Pipedrive access needed -- read-only against the registry via the webhook.

USAGE
  python dnc_gate_check.py leads.csv
  python dnc_gate_check.py leads.json

CSV must have a header row with at least one of: email, linkedin_url (any casing/spacing in the
header is fine -- "LinkedIn URL", "Email Address", etc. are all recognized). Any other columns
are passed through untouched and appear in the result.

JSON must be either a bare array of {email, linkedin_url, ...} objects, or {"rows": [...]}.
"""
import csv
import json
import os
import re
import sys
import urllib.request

GATE_URL = "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_DNC_PRE_ADD_GATE}}"


def _norm_header(h):
    return re.sub(r"[^a-z0-9]", "", h.lower())


def load_rows(path):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rows", data) if isinstance(data, dict) else data

    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header_map = {}
        for h in reader.fieldnames or []:
            n = _norm_header(h)
            if n in ("email", "emailaddress"):
                header_map[h] = "email"
            elif n in ("linkedinurl", "linkedin", "liurl", "profileurl"):
                header_map[h] = "linkedin_url"
        rows = []
        for raw in reader:
            row = {}
            for h, v in raw.items():
                key = header_map.get(h, h)
                row[key] = v
            rows.append(row)
        return rows


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    rows = load_rows(path)
    print(f"{len(rows)} rows loaded from {path}")

    req = urllib.request.Request(
        GATE_URL, method="POST",
        data=json.dumps({"rows": rows}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        result = json.loads(r.read())

    c = result["counts"]
    print(f"\nCLEAN: {c['clean']}   BLOCKED: {c['blocked']}   UNRESOLVABLE: {c['unresolvable']}\n")

    if c["blocked"]:
        print("BLOCKED:")
        for row in result["blocked"]:
            ident = row.get("email") or row.get("linkedin_url") or "?"
            print(f"  {ident}  -- {row.get('reason')}  (registry row {row.get('registry_row_ref')})")
    if c["unresolvable"]:
        print("\nUNRESOLVABLE (no email or LinkedIn URL -- check by hand):")
        for row in result["unresolvable"]:
            print(f"  {row}")

    out_path = os.path.splitext(path)[0] + "_gate_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"\nfull result (attach to the launch post): {out_path}")


if __name__ == "__main__":
    main()
