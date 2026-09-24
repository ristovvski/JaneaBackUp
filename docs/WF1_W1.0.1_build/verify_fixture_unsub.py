#!/usr/bin/env python3
"""Verify the fixture unsubscribe on the wire. `{"ok": true}` is a receipt, not a state.

The previous check looked for the lead on page 1 of /campaigns/{id}/leads - which returns the
OLDEST rows first, so a lead created 2026-08-06 was never going to be there. That was a broken
verifier, not necessarily a failed write.

Three independent reads instead, each printed in full:
  * /leads/?email=      - the global lead record and every field mentioning unsubscribe
  * leads-statistics    - the campaign-scoped view we already know paginates honestly
  * paged /campaigns/{id}/leads - walked until the lead is found, not just page 1
"""
import json, os, ssl, urllib.parse, urllib.request

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
CID, SL_LEAD, EMAIL = 3686187, "4306240392", "pii-c61c7d08@example.invalid"
API = "https://server.smartlead.ai/api/v1"


def call(path):
    url = f"{API}{path}{'&' if '?' in path else '?'}api_key={SLK}"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "janea/1.0"}), timeout=90, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)[:150]


print("A. global lead record")
st, d = call(f"/leads/?email={urllib.parse.quote(EMAIL)}")
print(f"   HTTP {st}")
if isinstance(d, dict):
    unsub_fields = {k: v for k, v in d.items() if "unsub" in k.lower() or "block" in k.lower()}
    print(f"   unsubscribe-ish fields: {json.dumps(unsub_fields)}")
    print(f"   all keys: {sorted(d.keys())}")

print("\nB. campaign-scoped view via leads-statistics")
st, d = call(f"/campaigns/{CID}/leads-statistics?limit=100")
rows = (d or {}).get("data") or [] if isinstance(d, dict) else []
me = [r for r in rows if str(r.get("lead_email", "")).lower() == EMAIL]
print(f"   HTTP {st}  rows={len(rows)}  matched={len(me)}")
for r in me:
    print(f"   {json.dumps({k: v for k, v in r.items() if k != 'history'})[:400]}")

print("\nC. paged /campaigns/{id}/leads until found (page 1 is the OLDEST rows)")
found = None
for off in range(0, 3000, 100):
    st, d = call(f"/campaigns/{CID}/leads?limit=100&offset={off}")
    rows = (d or {}).get("data") or [] if isinstance(d, dict) else []
    if not rows:
        print(f"   walked to offset {off}, no more rows")
        break
    hit = [r for r in rows
           if str((r.get("lead") or {}).get("email", "")).lower() == EMAIL]
    if hit:
        found = (off, hit[0])
        break
if found:
    off, r = found
    lead = r.get("lead") or {}
    print(f"   found at offset {off}")
    print(f"   status={r.get('status')!r}  is_unsubscribed(assoc)={r.get('is_unsubscribed')!r}")
    print(f"   lead.is_unsubscribed={lead.get('is_unsubscribed')!r}")
    print(f"   assoc keys: {sorted(r.keys())}")
    done = bool(r.get("is_unsubscribed")) or bool(lead.get("is_unsubscribed")) \
        or str(r.get("status", "")).upper() in ("UNSUBSCRIBED", "STOPPED", "PAUSED", "BLOCKED")
    print(f"\n   UNSUBSCRIBED CONFIRMED: {done}")
    if not done:
        print("   *** still active - the 200 did not change state; do it in the Smartlead UI ***")
else:
    print("   lead not found in any page - cannot confirm; treat as UNVERIFIED")
