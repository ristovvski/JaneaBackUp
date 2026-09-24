#!/usr/bin/env python3
"""READ-ONLY Smartlead endpoint diagnostics (fix limit; confirm webhook/email-account shapes)."""
import os, json, requests
K = os.environ["SMARTLEAD_API_KEY"]; B = "https://server.smartlead.ai/api/v1"
S = requests.Session()
def g(path, params=None):
    p = {"api_key": K}; p.update(params or {})
    try:
        r = S.get(B + path, params=p, timeout=45)
        try: body = r.json()
        except Exception: body = r.text[:300]
        return r.status_code, body
    except Exception as e:
        return None, str(e)[:200]

# one campaign id from the prior run
cid = 3686193
st, body = g("/email-accounts", {"offset": 0, "limit": 500})
print("GET /email-accounts (limit500):", st, "-> type", type(body).__name__,
      "len", (len(body) if isinstance(body, list) else "n/a"))
if isinstance(body, list) and body:
    ea = body[0]
    print("  email-account keys:", list(ea.keys())[:20])
st2, body2 = g("/campaigns/%s/webhooks" % cid)
print("GET /campaigns/%s/webhooks:" % cid, st2, "->", json.dumps(body2, ensure_ascii=False)[:500])
st3, body3 = g("/campaigns/%s/email-accounts" % cid)
print("GET /campaigns/%s/email-accounts:" % cid, st3, "-> type", type(body3).__name__,
      "len", (len(body3) if isinstance(body3, list) else "n/a"),
      json.dumps(body3, ensure_ascii=False)[:300] if not isinstance(body3, list) else "")
# account-level webhooks (some Smartlead setups)
st4, body4 = g("/webhooks")
print("GET /webhooks (account):", st4, "->", json.dumps(body4, ensure_ascii=False)[:300])
