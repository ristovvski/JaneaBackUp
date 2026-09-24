#!/usr/bin/env python3
"""READ-ONLY: full Pipedrive /webhooks record + resolve creator user_id -> name. Touch nothing."""
import os, json, requests
T = os.environ["PIPEDRIVE_API_TOKEN"]; B = "https://janeasystems.pipedrive.com/api/v1"
S = requests.Session()
wh = S.get(B + "/webhooks", params={"api_token": T}, timeout=45).json()
rows = wh.get("data") or []
users = {u["id"]: u for u in (S.get(B + "/users", params={"api_token": T}, timeout=45).json().get("data") or [])}
KEYS = ["id", "subscription_url", "event_action", "event_object", "user_id", "add_time",
        "remove_time", "is_active", "last_delivery_time", "last_http_status", "http_auth_user",
        "type", "name", "version"]
for w in rows:
    rec = {k: w.get(k) for k in KEYS}
    u = users.get(w.get("user_id"))
    rec["_creator_name"] = (u or {}).get("name")
    rec["_creator_email"] = (u or {}).get("email")
    rec["_creator_active"] = (u or {}).get("active_flag")
    print(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
print("TOTAL WEBHOOKS:", len(rows))
