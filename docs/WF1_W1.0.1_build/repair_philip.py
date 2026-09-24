#!/usr/bin/env python3
"""REPAIR — Person-9979a87c's InMail reply (exec 16703), which M7 dropped on a person-match miss.

Do exactly what M7 would have done and nothing more. His lead fb215d20 is HUMAN-owned (title
'Phil Cootey', no campaign field, two hand-written activities, owner 25733113) - so NO title
rewrite, NO campaign backfill, NO owner change. Those conventions are for leads we create.

M7 Labels Compute, targetStage 'Replied' (rank 4): targetSet = [cold, responded], UNIONED with the
existing labels - his human label is preserved.
M7 Reply Activity: type linkedin_messaging, done, participants[person], owner = melisa_user_id.

Deliberately NOT done: the person stage custom field patch. M7 would set it, but effectiveRank is a
max() so the next event self-heals, and this lead belongs to a human - minimum footprint wins.
"""
import argparse, json, os, ssl, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

LEAD = "fb215d20-94e7-11f1-9c86-a5bfb8f637e5"
PERSON = 85517
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
MELISA = 16340280
MSG = "Im heading back to Reston Virinia that week, what about the following week?"
WHEN = "2026-08-14T12:46:24.562Z"

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
a = ap.parse_args()


def pd(p, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + p, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": f"HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}"}


cur = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
existing = list(cur.get("label_ids") or [])
print(f"lead {LEAD}")
print(f"  title={cur.get('title')!r} owner={cur.get('owner_id')} archived={cur.get('is_archived')}")
print(f"  labels now ({len(existing)}): {existing}")

union = existing[:]
for lid in (L_COLD, L_RESPONDED):
    if lid not in union:
        union.append(lid)
print(f"  labels after union ({len(union)}): {union}")
print(f"  human label preserved: {existing[0] in union if existing else 'n/a'}")
if L_RESPONDED in existing:
    print("  responded already present - label write would be a no-op")

note = (f"LinkedIn InMail reply via Noah Keimach, {WHEN[:10]}:\n\n{MSG}\n\n"
        f"— Backfilled 2026-08-14. WF-1's M7 resolver could not match this person: HeyReach sends "
        f"https://www.linkedin.com/in/pii-7a798b9a and Pipedrive stores it without 'www.', so the "
        f"verbatim URL search returned 0 and the alert wrongly said 'not in Pipedrive'.")
act = {"subject": "LinkedIn reply", "type": "linkedin_messaging", "done": True,
       "participants": [{"person_id": PERSON, "primary": True}],
       "lead_id": LEAD, "owner_id": MELISA, "note": note,
       "due_date": WHEN[:10]}

print("\n=== PLANNED ===")
print(f"1. PATCH /v1/leads/{LEAD}  label_ids -> {len(union)} (union, nothing removed)")
print(f"2. POST /api/v2/activities")
print(json.dumps(act, indent=2, ensure_ascii=False)[:700])
print("\n  note: subject is 'LinkedIn reply' not M7's 'LinkedIn reply — <campaign>' because this "
      "event\n  carries campaign {} - M7's template would emit a dangling em-dash.")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
    raise SystemExit(0)

print("\n=== WRITING ===")
r1 = pd(f"/v1/leads/{LEAD}", "PATCH", {"label_ids": union})
got = ((r1.get("data") or {}).get("label_ids")) or []
print(f"  labels: {len(got)} {got}")
if r1.get("__err"):
    raise SystemExit(f"label PATCH failed: {r1['__err']}")
if L_RESPONDED not in got:
    raise SystemExit("responded NOT present after write - stopping")

r2 = pd("/api/v2/activities", "POST", act)
if r2.get("__err"):
    raise SystemExit(f"activity POST failed: {r2['__err']}")
aid = (r2.get("data") or {}).get("id")
print(f"  activity: {aid}")

back = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
acts = (pd(f"/api/v2/activities?lead_id={LEAD}&limit=20") or {}).get("data") or []
print(f"\n  READBACK labels={back.get('label_ids')}")
print(f"  READBACK activities={len(acts)}")
for x in acts:
    print(f"     {x.get('id')} {str(x.get('subject'))[:44]!r} {x.get('due_date')} "
          f"note={len(str(x.get('note') or ''))}ch")
print(f"\nLEAD_URL=https://janeasystems.pipedrive.com/leads/inbox/{LEAD}")
