#!/usr/bin/env python3
"""Snapshot the full current label_ids for every lead in the P1 incident's frozen 600, via
GET /v1/leads/{id} (same route R Get Lead By Id uses). Used both PRE-fire (baseline for the
byte-identical-other-labels post-verify, and source data for the handover-damage count) and
POST-fire (to diff against). Usage: python zz_p1_snapshot_leads.py <out.json>
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DNC_LABEL_ID = "52a7c290-fc73-11f0-ad98-81d4703453f3"
RESPONDED_LABEL_ID = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
FROZEN_IDS_PATH = os.path.join(HERE, "audit-artifacts", "p1_frozen_lead_ids_600.json")


def load_env():
    env_path = os.path.join(os.path.dirname(HERE), ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def main():
    if len(sys.argv) != 2:
        print("usage: python zz_p1_snapshot_leads.py <out.json>")
        sys.exit(2)
    out_path = sys.argv[1]
    load_env()
    token = os.environ["PIPEDRIVE_API_TOKEN"]

    with open(FROZEN_IDS_PATH, encoding="utf-8") as f:
        ids = json.load(f)["lead_ids"]

    results = []
    for i, lead_id in enumerate(ids):
        r = requests.get(f"https://api.pipedrive.com/v1/leads/{lead_id}",
                          params={"api_token": token}, timeout=30)
        if r.status_code == 404:
            results.append({"lead_id": lead_id, "found": False, "label_ids": None,
                             "has_dnc": None, "has_responded": None})
        else:
            r.raise_for_status()
            data = r.json().get("data") or {}
            labels = data.get("label_ids") or []
            results.append({
                "lead_id": lead_id, "found": True, "label_ids": labels,
                "has_dnc": DNC_LABEL_ID in labels,
                "has_responded": RESPONDED_LABEL_ID in labels,
            })
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(ids)}...")
        time.sleep(0.05)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"count": len(results), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "leads": results}, f, indent=2)
    found = sum(1 for r in results if r["found"])
    has_dnc = sum(1 for r in results if r.get("has_dnc"))
    has_resp = sum(1 for r in results if r.get("has_responded"))
    both = sum(1 for r in results if r.get("has_dnc") and r.get("has_responded"))
    print(f"wrote {out_path}: {len(results)} leads, found={found}, has_dnc={has_dnc}, "
          f"has_responded={has_resp}, both={both}")


if __name__ == "__main__":
    main()
