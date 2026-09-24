#!/usr/bin/env python3
"""READ-ONLY access confirmation. Calls GET /users/me — no data written, no list dumped."""
import os, requests
T = os.environ["PIPEDRIVE_API_TOKEN"]; B = "https://janeasystems.pipedrive.com/api/v1"
r = requests.get(B + "/users/me", params={"api_token": T}, timeout=30)
me = (r.json() or {}).get("data") or {}
print("status:", r.status_code)
print("authenticated as:", me.get("name"), "<" + str(me.get("email")) + ">",
      "| company:", (me.get("company_name")))
print("token scope check -> is_admin:", me.get("is_admin"), "| active:", me.get("active_flag"))
