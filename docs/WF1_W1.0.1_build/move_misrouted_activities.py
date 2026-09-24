#!/usr/bin/env python3
"""DEFECT 2 FIX — move the 121 misrouted outbound activities onto the campaign's own lead.

The first fire picked `active[0]` — the person's first non-archived lead — instead of the lead for
THIS campaign. Where a person also had an AI4 **2025** lead (2342830) or a HumanX lead, the 2026
email sends landed there. 121 activities, 31 people.

I under-reported this at first: I counted *leads whose campaign field mismatched* and got 1. That
missed every Make-created lead, because Make leaves the campaign field EMPTY — so a mismatch is
invisible to a field comparison and only shows up once routing is done properly and the destination
changes. The honest measure was "what does corrected routing choose differently", not "what looks
wrong in one field".

MOVE, not re-create: PATCH the activity's lead_id. Re-creating would leave the original behind and
double the record.

Guards: the destination lead must belong to the SAME person, and must already look like this
campaign's lead. A move that crosses people would be far worse than the misrouting it fixes.
"""
import argparse, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from collections import defaultdict

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = 3686181

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
        return {"__err": f"HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"__err": str(e)[:140]}


plan = json.load(open(os.path.join(HERE, f"outbound_backfill_plan_{CAMPAIGN}.json"),
                      encoding="utf-8"))["plan"]
want = defaultdict(list)          # correct lead -> [(key, email)]
for p in plan:
    want[p["body"]["lead_id"]].append((p["key"], p["email"]))
print(f"misrouted activities to move: {len(plan)} across {len(want)} destination leads")

moves, problems = [], []
for dest_lead, items in want.items():
    d = (pd(f"/v1/leads/{dest_lead}") or {}).get("data") or {}
    person = d.get("person_id")
    if not person:
        problems.append({"dest": dest_lead, "why": "destination lead has no person"})
        continue
    # every other active lead of the same person is a candidate holder
    holders = [l for l in ((pd(f"/v1/leads?limit=50&person_id={person}") or {}).get("data") or [])
               if l.get("id") != dest_lead]
    found = {}
    for h in holders:
        for act in ((pd(f"/api/v2/activities?lead_id={h.get('id')}&limit=100") or {})
                    .get("data") or []):
            m = re.search(r"\[key:([^\]]+)\]", str(act.get("note") or ""))
            if m:
                found[m.group(1)] = (act.get("id"), h.get("id"), str(h.get("title"))[:50])
    for key, email in items:
        hit = found.get(key)
        if not hit:
            problems.append({"key": key, "email": email, "why": "activity not found on any "
                                                                "other lead of this person"})
            continue
        act_id, from_lead, from_title = hit
        moves.append({"activity": act_id, "from_lead": from_lead, "from_title": from_title,
                      "to_lead": dest_lead, "person": person, "email": email, "key": key})

print(f"\nmoves resolved : {len(moves)}")
print(f"problems       : {len(problems)}")
for p in problems[:5]:
    print(f"   {p}")
print("\nsample moves:")
for m in moves[:5]:
    print(f"   {m['email']:<34} {m['from_title']!r}")
    print(f"      activity {m['activity']} -> lead {str(m['to_lead'])[:8]}")

# statics
ok = True
if len({m["activity"] for m in moves}) != len(moves):
    print("STATIC FAIL: an activity appears in more than one move")
    ok = False
cross = [m for m in moves if not m["person"]]
if cross:
    print(f"STATIC FAIL: {len(cross)} moves without a person")
    ok = False
print(f"\nSTATIC: every move stays within one person: "
      f"{'PASS' if ok else 'FAIL'}   ({len(moves)} activities, "
      f"{len({m['person'] for m in moves})} people)")

json.dump({"moves": moves, "problems": problems},
          open(os.path.join(HERE, f"move_plan_{CAMPAIGN}.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"artifact: move_plan_{CAMPAIGN}.json")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
    sys.exit(0)
if not ok:
    sys.exit("statics failed")

print("\n=== MOVING ===")
done = fail = 0
for i, m in enumerate(moves, 1):
    r = pd(f"/api/v2/activities/{m['activity']}", "PATCH", {"lead_id": m["to_lead"]})
    if r.get("__err"):
        fail += 1
        if fail <= 3:
            print(f"  FAIL {m['activity']}: {r['__err'][:120]}")
    else:
        done += 1
    if i % 40 == 0:
        print(f"  ...{i}/{len(moves)} moved={done} fail={fail}")
        time.sleep(1)
print(f"\nMOVED {done}   failed {fail}")

print("\n--- verification ---")
bad = 0
for m in moves[:60]:
    act = (pd(f"/api/v2/activities/{m['activity']}") or {}).get("data") or {}
    if str(act.get("lead_id")) != str(m["to_lead"]):
        bad += 1
print(f"  sampled 60 moved activities: {60 - bad} on the correct lead, {bad} not")
