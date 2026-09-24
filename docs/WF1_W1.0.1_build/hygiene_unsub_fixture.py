#!/usr/bin/env python3
"""Unsubscribe the fixture lead in Smartlead so it stops receiving sequence mail.

The fixture (pii-c61c7d08@example.invalid, campaign 3686187, SL lead 4306240392) has now driven three
reply tests. It must not keep receiving follow-ups.

Reads state BEFORE and AFTER and compares them: Smartlead has returned cheerful 200s for
no-op writes before, so "the call succeeded" is not evidence the lead is actually unsubscribed.
Tries the campaign-scoped endpoint first, then the global one, and reports which shape worked.
"""
import json, os, ssl, urllib.parse, urllib.request

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
CID, SL_LEAD, EMAIL = 3686187, "4306240392", "pii-c61c7d08@example.invalid"
API = "https://server.smartlead.ai/api/v1"


def call(path, method="GET", body=None):
    url = f"{API}{path}{'&' if '?' in path else '?'}api_key={SLK}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)[:150]


def state(tag):
    st, d = call(f"/campaigns/{CID}/leads?limit=100&offset=0")
    rows = (d or {}).get("data") or [] if isinstance(d, dict) else []
    me = [r for r in rows if str((r.get("lead") or {}).get("email", "")).lower() == EMAIL]
    if not me:
        st2, d2 = call(f"/leads/?email={urllib.parse.quote(EMAIL)}")
        print(f"  [{tag}] not in first page; /leads lookup HTTP {st2}: "
              f"{json.dumps(d2)[:160] if isinstance(d2, dict) else str(d2)[:160]}")
        return None
    r = me[0]
    lead = r.get("lead") or {}
    print(f"  [{tag}] status={r.get('status')!r} is_unsubscribed={lead.get('is_unsubscribed')!r} "
          f"unsubscribed_client_id={r.get('is_unsubscribed')!r}")
    return r


print("BEFORE")
before = state("before")

print("\nattempting unsubscribe")
attempts = [
    (f"/campaigns/{CID}/leads/{SL_LEAD}/unsubscribe", "POST", {}),
    (f"/leads/{SL_LEAD}/unsubscribe", "POST", {}),
]
worked = None
for path, method, body in attempts:
    st, d = call(path, method, body)
    print(f"  {method} {path} -> HTTP {st}  "
          f"{json.dumps(d)[:120] if isinstance(d, dict) else str(d)[:120]}")
    if st == 200:
        worked = path
        break

print("\nAFTER")
after = state("after")
print(f"\nendpoint that returned 200: {worked or 'NONE'}")
if after is not None:
    lead = after.get("lead") or {}
    done = bool(lead.get("is_unsubscribed")) or str(after.get("status", "")).upper() in (
        "UNSUBSCRIBED", "STOPPED", "PAUSED")
    print("UNSUBSCRIBED - verified by read-back" if done else
          "*** CALL RETURNED 200 BUT STATE DID NOT CHANGE - do it in the UI ***")
else:
    print("could not read state back - treat as UNVERIFIED, not as done")
