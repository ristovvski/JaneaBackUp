#!/usr/bin/env python3
"""READ-ONLY: verify /v1/leads/{uuid} and /v1/persons/{id}/changelog shapes live, on the
already-known Person-a644a93a duplicate-Slack-post case (lead c92f9670-8b36-11f1-8864-99ee038ec151,
Slack posts at 2026-08-04T07:08:37.337919Z and .454269Z UTC = 1785816517.xxx)."""
import os, json, requests
T = os.environ["PIPEDRIVE_API_TOKEN"]; B = "https://janeasystems.pipedrive.com/api/v1"
S = requests.Session()

lead = S.get(B + "/leads/c92f9670-8b36-11f1-8864-99ee038ec151", params={"api_token": T}, timeout=30).json()
ld = lead.get("data") or {}
print("LEAD keys:", sorted(ld.keys()))
person_id = ld.get("person_id")
print("person_id raw:", person_id, "type:", type(person_id).__name__)
if isinstance(person_id, dict):
    person_id = person_id.get("value")
    print("resolved person_id:", person_id)

cl = S.get(B + f"/persons/{person_id}/changelog", params={"api_token": T, "start": 0, "limit": 100}, timeout=30).json()
rows = cl.get("data") or []
print("\nCHANGELOG rows:", len(rows))
if rows:
    print("first row keys:", sorted(rows[0].keys()))
for r in rows:
    print(json.dumps({k: r.get(k) for k in ("time","field_key","actor_user_id","change_source",
          "change_source_user_agent","is_bulk_update_flag","old_value","new_value")},
          ensure_ascii=False, default=str))
