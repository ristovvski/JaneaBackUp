#!/usr/bin/env python3
"""Re-archive the Pipedrive fixture lead, now that the auditor has released it.

Read-back is the point: archived leads are invisible to LIST reads (archived_status is silently
ignored), so the check is that the person-scoped list read no longer returns it - the same call
WF-2 makes. A detail read still returning it is expected and is NOT a failure.
"""
import json, os, ssl, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
PERSON = 85506


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode("utf-8", "replace")


st, d = pd(f"/v1/leads/{LEAD}")
before = ((d or {}).get("data") or {}).get("is_archived") if isinstance(d, dict) else None
print(f"before: is_archived={before!r}")

st, d = pd(f"/v1/leads/{LEAD}", "PATCH", {"is_archived": True})
print(f"PATCH is_archived=true -> HTTP {st}")

st, d = pd(f"/v1/leads/{LEAD}")
after = ((d or {}).get("data") or {}).get("is_archived") if isinstance(d, dict) else None
print(f"after : is_archived={after!r}")

rows = (pd(f"/v1/leads?limit=100&person_id={PERSON}")[1] or {}).get("data") or []
visible = any(str(r.get("id")) == LEAD for r in rows)
print(f"\nperson-scoped LIST read (what WF-2 issues): {len(rows)} lead(s), "
      f"fixture visible={visible}")
for r in rows:
    print(f"   {str(r.get('id'))[:8]} archived={r.get('is_archived')} "
          f"{str(r.get('title'))[:52]!r}")
print("\nRE-ARCHIVED - and invisible to the list read WF-2 uses"
      if after is True and not visible else
      "\n*** NOT fully re-archived - check manually ***")
