#!/usr/bin/env python3
"""Close the three OOO handovers, then WATCH for regeneration.

Three real prospects are sitting in Slava's queue as actionable while they are on vacation
(back Aug 14 / 17 / 19). The '3. Responded' label has been removed, so Marci's automation should no
longer have its trigger condition.

The watch is the point, not a formality: if a handover comes back while the label is gone, the
automation keys off something OTHER than the live label - which changes what we believe about the
hydra, and we need to know that regardless of tonight. On regeneration this STOPS and reports
rather than fighting it in a loop.
"""
import json, os, ssl, sys, time, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
NOTE = "OOO auto-reply, not engagement — closed by automation cleanup"
LEADS = {"4ead0900-90d6-11f1-b07d-7faf1dbb463a": "pii-d5d243f4@example.invalid",
         "51c9f9d0-8538-11f1-8c6a-ef2edb9d15ea": "pii-9f313a1a@example.invalid",
         "17c6d0b0-8541-11f1-998a-a9f867fdc12c": "pii-08ce5db0@example.invalid"}
WATCH_S = int(os.environ.get("WATCH_S", "150"))


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


def open_handovers(lid):
    acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=50")[1] or {}).get("data") or []
    return [a for a in acts
            if str(a.get("type")) == "handover" and a.get("done") is not True]


print("--- closing ---")
closed = []
for lid, em in LEADS.items():
    for act in open_handovers(lid):
        aid = act.get("id")
        st, r = pd(f"/api/v2/activities/{aid}", "PATCH", {"done": True, "note": NOTE})
        st2, d2 = pd(f"/api/v2/activities/{aid}")
        now = (d2 or {}).get("data") or {} if isinstance(d2, dict) else {}
        ok = now.get("done") is True
        print(f"   {em:<28} activity {aid}: PATCH {st} -> done={now.get('done')!r} "
              f"{'OK' if ok else 'NOT CLOSED'}")
        if ok:
            closed.append((em, aid))
        else:
            print(f"      response: {str(r)[:160]}")
print(f"closed: {len(closed)}")

print(f"\n--- watching {WATCH_S}s for regeneration (the hydra reappears in ~3s when armed) ---")
deadline = time.time() + WATCH_S
regenerated = []
while time.time() < deadline:
    time.sleep(15)
    for lid, em in LEADS.items():
        fresh = open_handovers(lid)
        for a in fresh:
            if (em, a.get("id")) in regenerated:
                continue
            regenerated.append((em, a.get("id")))
            print(f"   *** REGENERATED: {em} activity {a.get('id')} "
                  f"add_time={a.get('add_time')} ***")
    if regenerated:
        break
    print(f"   {int(deadline - time.time())}s left, all quiet")

print()
if regenerated:
    print("STOP - handovers regenerated while the '3. Responded' label is ABSENT.")
    print("That means Marci's automation triggers on something other than the live label.")
    print("Not fighting it in a loop; reporting instead:")
    for em, aid in regenerated:
        print(f"   {em}  activity {aid}")
    sys.exit(1)

print("CLEAN - no regeneration inside the watch window.")
for lid, em in LEADS.items():
    acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=50")[1] or {}).get("data") or []
    h = [a for a in acts if str(a.get("type")) == "handover"]
    print(f"   {em:<28} handovers={len(h)} all_done={all(a.get('done') is True for a in h)}")
