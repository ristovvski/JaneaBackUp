#!/usr/bin/env python3
"""§9f.2 artifact — Finovate backfill, CONTACTED-ONLY (Nik's ruling).

Scope: people we have actually touched who still have no lead.
  email     : all 9 have a SENT
  LinkedIn  : connection status ConnectionSent or ConnectionAccepted only
The remaining ~110 uncontacted list members are deliberately EXCLUDED - they get their leads from
the live pipeline at first touch. Standing rule now: "membership = existence" executes at FIRST
TOUCH, not at list-load.

Names are provider truth (Smartlead / HeyReach profile). Never derived from an address.
Open-deal guard applied: anyone with an open deal is dropped, not given a competing lead.

READ ONLY - writes finovate_backfill_map.json.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
CAMP_NAMES = {3868449: "[Events Visiting] [FinovateFall 2026] - Noah - Valids",
              3868450: "[Events Visiting] [FinovateFall 2026] - Noah - Catch-alls",
              572715: "[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn"}
NOAH = 25733113          # campaign sender = owner, per the ruling
COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
OPP_VALUE = 480
CHANNEL = 578


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


email_pop = json.load(open(os.path.join(HERE, "finovate_population.json"),
                           encoding="utf-8"))["members"]
li_pop = json.load(open(os.path.join(HERE, "finovate_heyreach_population.json"),
                        encoding="utf-8"))["members"]

# ---- email side: no lead AND actually sent (verified earlier - all 9 were)
gap_detail = json.load(open(os.path.join(HERE, "finovate_gap_detail.json"), encoding="utf-8"))
sent_emails = {g["email"] for g in gap_detail["sent_no_lead"]}
email_rows = [r for r in email_pop
              if r["state"] in ("nothing", "person_only") and r["email"] in sent_emails]

# ---- LinkedIn side: no lead AND contacted
CONTACTED = {"ConnectionSent", "ConnectionAccepted"}
li_rows = [r for r in li_pop
           if r["state"] in ("nothing", "person_only")
           and str(r.get("connection")) in CONTACTED]

print(f"email  candidates (sent, no lead)      : {len(email_rows)}")
print(f"linkedin candidates (contacted, no lead): {len(li_rows)}")
print(f"  excluded uncontacted LinkedIn members : "
      f"{len([r for r in li_pop if r['state'] != 'has_lead']) - len(li_rows)}")
print(f"  connection mix of the LinkedIn set     : "
      f"{dict(Counter(str(r.get('connection')) for r in li_rows))}")

plan = []
for r in email_rows:
    full = " ".join(filter(None, [r.get("first"), r.get("last")])).strip()
    plan.append({
        "channel": "email", "email": r["email"], "person_id": r.get("person_id"),
        "campaign_id": r["campaign_id"], "campaign": CAMP_NAMES[r["campaign_id"]],
        "segment": r["segment"], "first": r.get("first"), "last": r.get("last"),
        "company": r.get("company"), "linkedin": None,
        "full_name": full or None,
        "lead_title": f"{r['campaign_id']} - {CAMP_NAMES[r['campaign_id']]} - {full}".strip(" -"),
    })
for r in li_rows:
    full = " ".join(filter(None, [r.get("first"), r.get("last")])).strip()
    plan.append({
        "channel": "linkedin", "email": None, "person_id": r.get("person_id"),
        "campaign_id": 572715, "campaign": CAMP_NAMES[572715],
        "segment": str(r.get("connection")), "first": r.get("first"), "last": r.get("last"),
        "company": r.get("company"), "linkedin": r.get("profile_url"),
        "full_name": full or None,
        "lead_title": f"572715 - {CAMP_NAMES[572715]} - {full}".strip(" -"),
    })

# ---- guards applied at map time (re-applied at write time)
noname = [p for p in plan if not p["full_name"]]
dealed = []
for p in plan:
    if p.get("person_id"):
        dl = (pd(f"/api/v2/deals?person_id={p['person_id']}&status=open&limit=5")
              or {}).get("data") or []
        if dl:
            dealed.append(p)
plan = [p for p in plan if p["full_name"] and p not in dealed]

print(f"\nDROPPED — no provider name          : {len(noname)}")
print(f"DROPPED — person has an OPEN DEAL   : {len(dealed)}")
print(f"\nFINAL BACKFILL SET                  : {len(plan)}")
print(f"  by channel: {dict(Counter(p['channel'] for p in plan))}")
print(f"  needs a person created first: {sum(1 for p in plan if not p['person_id'])}")

print("\n--- 5 example rows ---")
for p in plan[:5]:
    print(f"  [{p['channel']:<8}] {p['full_name']!r} ({p['company']})")
    print(f"      person: {p['person_id'] or 'CREATE'}   owner: Noah ({NOAH})")
    print(f"      lead  : {p['lead_title'][:72]!r}")

json.dump({"plan": plan, "dropped_noname": noname, "dropped_open_deal": dealed,
           "owner_id": NOAH, "label": COLD},
          open(os.path.join(HERE, "finovate_backfill_map.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: finovate_backfill_map.json")
