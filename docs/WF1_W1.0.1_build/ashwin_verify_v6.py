#!/usr/bin/env python3
"""READ-ONLY. The v5 person-changelog check can under-report Make: scenario 8557478 writes the
'responded' LABEL onto the LEAD, and lead changes do not appear in a person's changelog. So check
the leads themselves - resolve label_ids to names and read each lead's update_time vs the reply.
This is the decisive business-impact evidence for step 5.
"""
import json, os, ssl, time
from datetime import datetime, timezone
import urllib.error, urllib.parse, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

TARGETS = [
    ("2026-08-04T15:10:03+00:00", "pii-67425a37@example.invalid", 83538, "Out Of Office"),
    ("2026-08-04T16:15:03+00:00", "pii-b02b50cf@example.invalid", 53341, "Out Of Office"),
    ("2026-08-04T16:31:45+00:00", "pii-6f8f48e5@example.invalid", 83546, "(history-only)"),
    ("2026-08-04T16:38:45+00:00", "pii-135b4c7b@example.invalid", 83756, "(history-only)"),
    ("2026-08-04T16:38:45+00:00", "pii-90ec4caf@example.invalid", 83651, "Out Of Office"),
    ("2026-08-04T16:55:41+00:00", "pii-567b1851@example.invalid", 83648, "Interested"),
    ("2026-08-04T17:04:26+00:00", "pii-06275333@example.invalid", 84737, "Out Of Office"),
    ("2026-08-04T19:10:59+00:00", "pii-7b1c0e1a@example.invalid", 84086, "Not Interested"),
    ("2026-08-05T06:08:38+00:00", "pii-280f963f@example.invalid", 83606, "Wrong Person"),
]
# control: a reply from BEFORE the outage that both systems handled
CONTROL = [("2026-08-03T16:54:19+00:00", "pii-0ddf11ef@example.invalid", None, "Meeting Request")]


def _get(url, headers, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code}
        except Exception:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": "net"}
    return {}


def pd(path, params=None):
    q = dict(params or {}); q["api_token"] = PDT
    return _get(f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


labels = pd("/leadLabels")
LAB = {L["id"]: L.get("name") for L in ((labels or {}).get("data") or [])}
print("lead labels in this org:", json.dumps(LAB, ensure_ascii=False))

rows = []
for rts, email, pid, cat in CONTROL + TARGETS:
    if pid is None:
        srch = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true"})
        items = ((srch or {}).get("data") or {}).get("items") or []
        pid = items[0]["item"]["id"] if items else None
    if pid is None:
        print(f"\n{rts}  {email}  -> no person"); continue
    lds = pd("/leads", {"limit": 100, "person_id": pid, "archived_status": "all"})
    lead_rows = (lds or {}).get("data") or []
    rt = ts(rts)
    print(f"\n{rts}  {email:<36} [{cat}]  person #{pid}  leads={len(lead_rows)}")
    for L in lead_rows:
        names = [LAB.get(x, x) for x in (L.get("label_ids") or [])]
        ut = ts(L.get("update_time"))
        when = "AFTER reply" if (ut and rt and ut >= rt) else "before reply"
        print(f"    lead {L.get('id')[:8]}  labels={names}  update_time={L.get('update_time')}"
              f"  ({when})")
        print(f"        title={str(L.get('title'))[:70]}")
        rows.append({"reply_time": rts, "email": email, "category": cat, "person_id": pid,
                     "lead_id": L.get("id"), "labels": names,
                     "update_time": L.get("update_time"), "updated_after_reply": when})

# NB: the label is literally '3. Responded' - a startswith('respond') test silently returns 0.
responded = [r for r in rows if any("respond" in str(n).lower() for n in r["labels"])]
fresh = [r for r in responded if r["updated_after_reply"] == "AFTER reply"]
print("\n" + "-" * 100)
print(f"leads carrying a 'Responded'-type label at all: {len(responded)} / {len(rows)}")
for r in responded:
    print(f"   {r['email']:<36} labels={r['labels']}  ({r['updated_after_reply']})")
print(f"\nof those, label demonstrably applied AFTER this reply (i.e. THIS reply was handled): "
      f"{len(fresh)}")
for r in fresh:
    print(f"   {r['email']:<36} update_time={r['update_time']}")
print("\nleads with NO responded-handling attributable to this reply:")
for r in rows:
    if r not in fresh:
        print(f"   {r['reply_time']}  {r['email']:<36} [{r['category']}] labels={r['labels']}")

with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_verify_v6.json"), "w",
          encoding="utf-8") as f:
    json.dump({"labels": LAB, "leads": rows}, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_verify_v6.json")
