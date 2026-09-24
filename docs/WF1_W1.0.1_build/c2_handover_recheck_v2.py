#!/usr/bin/env python3
"""Re-run the C2 Handover guard with /api/v2 — c2_handover_guard_check.py used
/v1/activities?lead_id=, which returns data:null for lead-attached activities and therefore
reported ZERO no matter what was there.

Scope, per the owner's ask, checked EMPIRICALLY rather than argued from the label set:
  A. the backfill-25 leads that actually received '3. Responded' (the real exposure)
  B. all 300 backfill-300 leads (created 2026-08-05, owner Melisa, cold-only) - the task log
     concluded no Handover could fire because the automation keys on 'responded'. That reasoning
     is sound but was never measured. Measure it.
  C. every other Melisa-owned lead carrying '3. Responded' with an open handover, so the number
     Melisa is given is the real one and not just our two backfills.

READ-ONLY. No closes - the owner's standing decision is LEAVE handovers as a legitimate queue.
"""
import json, os, ssl, urllib.error, urllib.parse, urllib.request
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-c2-recheck/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
MELISA = 16340280
B25 = ("a81299b0", "8d9a2ab0")            # Person-ef1ea617, Andrew Miller-McKeever


def pd(path):
    try:
        r = urllib.request.Request("https://api.pipedrive.com" + path,
                                   headers={"x-api-token": PDT, "User-Agent": UA})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code}
    except Exception as e:
        return {"__err": str(e)[:150]}


leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
print(f"leads loaded: {len(leads)}")

b25 = [L for L in leads if str(L.get("id", "")).startswith(B25)]
b300 = [L for L in leads if str(L.get("add_time") or "").startswith("2026-08-05")
        and L.get("owner_id") == MELISA and (L.get("label_ids") or []) == [COLD]]
resp_melisa = [L for L in leads if RESPONDED in (L.get("label_ids") or [])
               and L.get("owner_id") == MELISA]
print(f"  A. backfill-25 responded leads found: {len(b25)}")
print(f"  B. backfill-300 leads (2026-08-05, Melisa, cold-only): {len(b300)}")
print(f"  C. all Melisa-owned leads carrying '3. Responded': {len(resp_melisa)}")


def opens(lead_id):
    acts = (pd(f"/api/v2/activities?lead_id={lead_id}&limit=100") or {}).get("data") or []
    return [a for a in acts if not a.get("done")]


def sweep(name, rows, show_all=False):
    print(f"\n{'='*100}\n{name}  ({len(rows)} leads)\n{'='*100}")
    hits, tally = [], Counter()
    for i, L in enumerate(rows):
        op = opens(L["id"])
        for a in op:
            tally[str(a.get("type"))] += 1
        ho = [a for a in op if str(a.get("type")) == "handover"]
        if ho:
            hits.append({"lead_id": L["id"], "title": L.get("title"),
                         "handovers": [{"id": a["id"], "subject": a.get("subject"),
                                        "add_time": a.get("add_time")} for a in ho]})
        if show_all or ho:
            if ho:
                print(f"  {str(L['id'])[:8]}  {str(L.get('title'))[:58]:<58} "
                      f"open handovers={len(ho)}  first_add={ho[0].get('add_time')}")
        if (i + 1) % 50 == 0:
            print(f"    ...{i+1}/{len(rows)} scanned")
    print(f"  -> leads with an OPEN handover: {len(hits)} / {len(rows)}")
    print(f"  -> open activity types across the set: {dict(tally)}")
    return hits, dict(tally)


out = {}
out["b25"], out["b25_types"] = sweep("A. backfill-25 (received '3. Responded')", b25, True)
out["b300"], out["b300_types"] = sweep("B. backfill-300 (cold-only)", b300)
out["resp_melisa"], out["resp_types"] = sweep(
    "C. every Melisa-owned lead carrying '3. Responded'", resp_melisa)

print("\n" + "=" * 100)
print("VERDICT")
print("=" * 100)
print(f"  backfill-25   : {len(out['b25'])} lead(s) with an open handover the v1 guard could not see")
print(f"  backfill-300  : {len(out['b300'])} lead(s) with an open handover "
      f"({'confirms the cold-only reasoning' if not out['b300'] else 'CONTRADICTS the task-log reasoning'})")
print(f"  Melisa queue  : {len(out['resp_melisa'])} responded-lead(s) with an open handover in total")

with open(os.path.join(HERE, "wf1-release-evidence", "c2_handover_recheck_v2.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/c2_handover_recheck_v2.json")
