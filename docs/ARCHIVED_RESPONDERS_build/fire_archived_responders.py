#!/usr/bin/env python3
"""Transform classification_final.json into DNC__UpsertLedger__v1-valid rows and fire them via
dnc_archived_responders_import (dry_run by default -- pass --live to actually write).

Mapping decisions (see ARTIFACT_prefire.md for the full rationale):
  - classify.py's own 'explicit_opt_out' bucket -> registry reason 'unsubscribe' (NOT
    'explicit_opt_out', which is an ENTRY_TYPE value in reason_v1.js, not a valid `reason`).
  - the 6 possible_opt_out rows I assessed as genuine (per ARTIFACT_prefire.md #4) are promoted
    to 'unsubscribe' here; the 4 I assessed as likely quote-artifacts stay 'reply_dnc'.
  - every reply_dnc row gets a reply_category derived from the CSV's own Lead-Labels field
    (real signal already in hand, no extra live calls) -- never the bare 'unclassified'
    placeholder when better information exists.
  - the 1 no-identifier row (Lule Salihu duplicate) is excluded -- structurally unfireable
    (UpsertLedger needs an identity to match against) and not merged by name alone.
"""
import json, os, ssl, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

# my own read from ARTIFACT_prefire.md #4 -- genuine own-words stop-language, no quote-marker
# contamination detected in the visible text.
GENUINE_POSSIBLE_OPT_OUT = {
    "Miguel Martín", "Person-ce02caf6", "James Ding", "Person-92ee42c2", "Person-26fc20bc", "Person-fc62ec56",
}


def reply_category_from_labels(labels):
    l = labels or ""
    if "5. Meeting" in l:
        return "meeting_no_conversion"
    if "4. Positive Reply" in l:
        return "positive_reply_no_conversion"
    if "NOT INTERESTED" in l:
        return "not_interested"
    if "Disqualified" in l:
        return "disqualified_generic"
    return "responded_generic"


def build_rows():
    with open(os.path.join(HERE, "classification_final.json"), encoding="utf-8") as f:
        d = json.load(f)
    rows = []
    skipped_no_identity = []
    for r in d["rows"]:
        if r["identity_key"] is None:
            skipped_no_identity.append(r["person_name"] or r["lead_title"])
            continue
        campaign = r.get("campaign") or None
        source_ref = campaign or "melisa_archived_export_2026-08-28"
        if r.get("human_review"):
            source_ref += " [flagged: " + ("possible_opt_out" if "possible_opt_out_evidence" in r else "unreadable_reply") + "]"
        base = {
            "email": r["email"], "linkedin_url": r["linkedin_url"], "full_name": r["person_name"] or None,
            "source": "archived_responders_export", "source_ref": source_ref,
            "correlation_id": "archived_responders_2026-08-28:" + r["identity_key"],
            "date_precision": "derived", "expiry_review_pending": False,
        }
        promote = r["person_name"] in GENUINE_POSSIBLE_OPT_OUT
        if r["reason"] == "explicit_opt_out" or promote:
            row = dict(base, reason="unsubscribe")
        else:
            row = dict(base, reason="reply_dnc", reply_category=reply_category_from_labels(r["labels"]))
        rows.append(row)
    return rows, skipped_no_identity


def n8n_public(path, method="POST", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE.replace("/api/v1", "") + path, method=method, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.loads(x.read())


def main():
    live = "--live" in sys.argv
    rows, skipped = build_rows()
    print(f"rows to fire: {len(rows)}  (skipped, no identity: {len(skipped)} -> {skipped})")
    n_unsub = sum(1 for r in rows if r["reason"] == "unsubscribe")
    n_reply = sum(1 for r in rows if r["reason"] == "reply_dnc")
    print(f"  reason=unsubscribe: {n_unsub}   reason=reply_dnc: {n_reply}")
    cats = {}
    for r in rows:
        if r["reason"] == "reply_dnc":
            cats[r["reply_category"]] = cats.get(r["reply_category"], 0) + 1
    print("  reply_category breakdown:", cats)

    body = {"rows": rows, "dry_run": not live}
    result = n8n_public("/webhook/{{WEBHOOK_DNC_ARCHIVED_RESPONDERS_IMPORT}}", body=body)
    print("\nresult:", json.dumps(result, indent=1, ensure_ascii=False)[:2000])
    with open(os.path.join(HERE, "fire_result.json"), "w", encoding="utf-8") as f:
        json.dump({"request_rows": len(rows), "skipped_no_identity": skipped, "live": live, "result": result},
                  f, indent=1, ensure_ascii=False)
    print("wrote fire_result.json")


if __name__ == "__main__":
    main()
