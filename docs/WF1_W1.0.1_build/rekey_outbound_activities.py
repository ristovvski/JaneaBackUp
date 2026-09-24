#!/usr/bin/env python3
"""DEFECT 1 FIX — re-key the 983 written outbound activities from stats_id to message_id.

`stats_id` is NOT unique: Smartlead reuses it across follow-up sends in the same thread (the
message_id gains a `-slt<N>-` infix while stats_id stays put). Measured across the AI4 family:

    campaign   SENT   collisions on (lead,stats_id)   on (lead,message_id)
    3686181     985                 9                        0
    3686184     786                14                        4   <- byte-identical feed dupes
    3686187     798                 9                        0
    3686193     878                19                        0

`email_seq_number` was IDENTICAL across every collision, so "stats_id|step" would not have fixed
anything. `stats_id|time` works, but message_id is better for a reason worth stating: where
message_id DOES collide (3686184, one lead returned twice by the feed), the rows are byte-identical
duplicates — so collapsing them is correct. A time-based key would faithfully write the same
activity twice.

CANONICAL KEY, both paths, past and future:  O|SL|<message_id>

This script only edits the `[key:...]` footer line of already-written notes. Nothing else in the
note, and no other field, is touched.
"""
import argparse, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from collections import defaultdict

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("--campaign", type=int, default=3686181)
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


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


# ---- provider truth: (stats_id, time) -> message_id
xref = {}
off = 0
while off < 3000:
    r = sl(f"/campaigns/{a.campaign}/leads-statistics", limit=100, offset=off)
    rows = (r or {}).get("data") or []
    if not rows:
        break
    for row in rows:
        for h in (row.get("history") or []):
            if str(h.get("type") or "").upper() != "SENT":
                continue
            xref[(str(h.get("stats_id")), str(h.get("time")))] = str(h.get("message_id") or "")
    if not r.get("hasMore"):
        break
    off += 100
print(f"provider xref (stats_id,time) -> message_id : {len(xref)} entries")

plan = json.load(open(os.path.join(HERE, f"outbound_backfill_plan_{a.campaign}.json"),
                      encoding="utf-8"))["plan"]
lead_ids = {p["body"].get("lead_id") for p in plan if p["body"].get("lead_id")}
print(f"leads to sweep: {len(lead_ids)}")

KEYRE = re.compile(r"\[key:(O\|SL\|[^\]]+)\]")
TIMERE = re.compile(r"·\s*(\d{4}-\d{2}-\d{2}T[\d:.]+\+?[\d:]*)")
todo, unmatched, already, scanned = [], [], 0, 0
for i, lid in enumerate(lead_ids, 1):
    acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []
    for act in acts:
        note = str(act.get("note") or "")
        m = KEYRE.search(note)
        if not m:
            continue
        scanned += 1
        old = m.group(1)
        if not old.startswith("O|SL|") or old.count("|") != 2:
            already += 1
            continue
        sid = old.split("|", 2)[2]
        tm = TIMERE.search(note)
        mid = xref.get((sid, tm.group(1))) if tm else None
        if not mid:
            cands = [v for (s, t), v in xref.items() if s == sid]
            if len(cands) == 1:
                mid = cands[0]
        if not mid:
            unmatched.append({"activity": act.get("id"), "old": old,
                              "time": tm.group(1) if tm else None})
            continue
        new = f"O|SL|{mid}"
        if new == old:
            already += 1
            continue
        todo.append({"activity": act.get("id"), "lead_id": lid, "old": old, "new": new,
                     "note": KEYRE.sub(f"[key:{new}]", note, count=1)})
    if i % 60 == 0:
        print(f"  ...{i}/{len(lead_ids)} leads  to re-key={len(todo)} unmatched={len(unmatched)}")

print(f"\nactivities carrying a key : {scanned}")
print(f"to re-key                 : {len(todo)}")
print(f"already canonical         : {already}")
print(f"UNMATCHED (would be left) : {len(unmatched)}")
for u in unmatched[:5]:
    print(f"   {u}")
newkeys = [t["new"] for t in todo]
print(f"new keys distinct         : {len(set(newkeys))}/{len(newkeys)}"
      f"{'  OK' if len(set(newkeys)) == len(newkeys) else '  <-- STILL COLLIDING'}")

# the 9 collision cases must now produce 9 distinct keys
oldc = defaultdict(list)
for t in todo:
    oldc[t["old"]].append(t["new"])
coll = {k: v for k, v in oldc.items() if len(v) > 1}
print(f"\nSTATIC — old keys that were shared: {len(coll)}")
allok = True
for k, v in coll.items():
    ok = len(set(v)) == len(v)
    allok = allok and ok
    print(f"   {k[:44]}  x{len(v)} -> {len(set(v))} distinct  {'ok' if ok else 'FAIL'}")
print(f"STATIC RESULT: {'PASS - every collision now resolves to distinct keys' if allok and coll else ('PASS (no collisions in scope)' if allok else 'FAIL')}")

json.dump({"todo": todo, "unmatched": unmatched},
          open(os.path.join(HERE, f"rekey_plan_{a.campaign}.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"artifact: rekey_plan_{a.campaign}.json")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
    sys.exit(0)
if not allok:
    sys.exit("statics failed - refusing to write")

print("\n=== WRITING ===")
ok = fail = 0
for i, t in enumerate(todo, 1):
    r = pd(f"/api/v2/activities/{t['activity']}", "PATCH", {"note": t["note"]})
    if r.get("__err"):
        fail += 1
        if fail <= 3:
            print(f"  FAIL {t['activity']}: {r['__err'][:110]}")
    else:
        ok += 1
    if i % 100 == 0:
        print(f"  ...{i}/{len(todo)} ok={ok} fail={fail}")
        time.sleep(1)
print(f"\nRE-KEYED {ok}   failed {fail}")
