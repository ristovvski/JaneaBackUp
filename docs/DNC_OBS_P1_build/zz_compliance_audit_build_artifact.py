#!/usr/bin/env python3
"""Assemble the final compliance-audit artifact from all the recon fixtures collected. Read-only."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

dist = json.load(open(os.path.join(FIX, "compliance_audit_distribution.json"), encoding="utf-8"))
offboard = json.load(open(os.path.join(FIX, "offboard_eligible_investigate.json"), encoding="utf-8"))
manual_sheet = json.load(open(os.path.join(FIX, "manual_sheet_check.json"), encoding="utf-8"))

COMPLIANT_KEYS = {
    "employee_connection | manual_offboard_eligible",
    "negative_reply | reply_dnc",
    "negative_reply | meeting_dnc",
    "replied | meeting_dnc",
    "explicit_opt_out | client",
    "employee_connection | sales_personal_outreach",
    "manual | sales_personal_outreach",
}
NONCOMPLIANT_KEYS = {
    "manual | event_contacted",
    "manual | manual_sheet",
}

total_compliant = sum(r["count"] for r in dist["distribution"] if r["key"] in COMPLIANT_KEYS)
total_noncompliant = sum(r["count"] for r in dist["distribution"] if r["key"] in NONCOMPLIANT_KEYS)
unclassified = [r for r in dist["distribution"] if r["key"] not in COMPLIANT_KEYS and r["key"] not in NONCOMPLIANT_KEYS]

print(f"Total active: {dist['total_active']}")
print(f"COMPLIANT: {total_compliant}")
print(f"NON-COMPLIANT: {total_noncompliant}")
print(f"Sum check: {total_compliant + total_noncompliant} (should equal total_active)")
print(f"Unclassified combos (should be empty): {unclassified}")

manifest = {
    "ruling": "Registry compliance audit vs Melisa's rule, 2026-08-26",
    "removed_reason_tag": "rule_change_2026-08-26_melisa",
    "total_active": dist["total_active"],
    "total_compliant": total_compliant,
    "total_noncompliant": total_noncompliant,
    "compliant_breakdown": [r for r in dist["distribution"] if r["key"] in COMPLIANT_KEYS],
    "noncompliant_breakdown": [r for r in dist["distribution"] if r["key"] in NONCOMPLIANT_KEYS],
    "employee_connection_note": (
        f"24,201-row employee_connection/manual_offboard_eligible bucket investigated: "
        f"{offboard['with_pid']} carry a Pipedrive person id, {offboard['without_pid']} don't. "
        f"ALL from seed_2026-08-11:people_dnc_pass1 (2026-08-07 bulk import), source="
        f"onboarding_import:<sales rep name> (Jim 8365, Toby 4116, Mario 2404, Noah Keimach 2159, "
        f"Rune 1801, Mario Stalder 1546, Matt Carothers 1459, Benedetto 1361, Mike CEO 671, "
        f"Sergey Cujba 169, +smaller), owner_tag PRE-POPULATED with that same rep's name on "
        f"every row. Reads as genuine personal/employee connections per rep, classified COMPLIANT "
        f"under the literal rule (employee_connection is a named keeper category) -- flagging "
        f"prominently given its scale (73% of the whole registry) rather than passing silently."
    ),
    "manual_sheet_note": (
        f"348 manual/manual_sheet rows checked for hidden reply evidence: same 2026-08-07 seed "
        f"import (onboarding_import:people_dnc_csv, onboarding_import:Pipedrive), zero also_flagged "
        f"signals, no reply/meeting/sales attribution anywhere. NON-COMPLIANT, no reply evidence."
    ),
}
with open(os.path.join(FIX, "compliance_audit_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=1)
print("wrote fixtures/compliance_audit_manifest.json")
