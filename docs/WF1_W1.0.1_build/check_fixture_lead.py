#!/usr/bin/env python3
"""Is fixture lead 72ec85c0 visible to LIST reads again after Nik un-archived it?

Detail-read visibility is NOT the test. Archived leads were always readable by id; what made the
fixture useless was that archived leads are invisible to /v1/leads LIST reads (archived_status is
silently ignored), and list reads are what WF-2's resolution uses. So the check that matters is:
does the PERSON-SCOPED list read - the exact call `R Lead List` now makes - return it?

Single-record reads only; the auditor still has Pipedrive priority.
"""
import json, os, ssl, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
PERSON = 85506


def pd(p):
    try:
        rq = urllib.request.Request("https://api.pipedrive.com" + p,
                                    headers={"x-api-token": PDT, "User-Agent": "janea/1.0"})
        with urllib.request.urlopen(rq, timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read FAILED (not empty): {str(e)[:110]}")
        return None


d = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
print("detail read:")
for k in ("id", "title", "person_id", "is_archived", "add_time", "update_time"):
    print(f"   {k:<13} {d.get(k)!r}")
print(f"   label_ids     {d.get('label_ids')}")

rows = (pd(f"/v1/leads?limit=100&person_id={PERSON}") or {}).get("data") or []
found = [l for l in rows if str(l.get("id")) == LEAD]
print(f"\nperson-scoped LIST read (what R Lead List issues): {len(rows)} lead(s) for person {PERSON}")
for l in rows:
    print(f"   {str(l.get('id'))[:8]}  archived={l.get('is_archived')}  "
          f"{str(l.get('title'))[:58]!r}")

ok = bool(found) and d.get("is_archived") is False
print(f"\nvisible to list reads again: {bool(found)}")
print(f"is_archived is False        : {d.get('is_archived') is False}")
print("\nFIXTURE READY - the reply will resolve this lead" if ok else
      "\n*** NOT READY - it is still invisible to the list read WF-2 uses ***")
