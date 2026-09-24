#!/usr/bin/env python3
"""FIRE — Finovate contacted-only backfill: 9 persons + 9 leads. SILENT (no alerts, no activities,
no labels beyond '1. Cold'), per the ruling.

Guards, re-applied per record at write time:
  * still no lead for this person/email (someone may have created one since the map was built)
  * still no OPEN DEAL (the Andrea guard - a person represented by a deal never gets a competing lead)
  * provider name required; person is created with the first/last PAIR, never an email-derived name
Post-run: verify the class is empty by re-deriving it, not by re-reading the plan.
"""
import argparse, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
F_COMPANY = "5a282f55e910cceeb960969460b8409b4c10d623"
F_CAMPAIGN = "86157bb49563191c17b4dc62580525f84417524c"
OPP_VALUE = 480
CHANNEL = 578
NOAH = 25733113

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
        return {"__err": f"HTTP {e.code} {e.read()[:220].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"__err": str(e)[:140]}


PLAN = json.load(open(os.path.join(HERE, "finovate_backfill_map.json"),
                      encoding="utf-8"))["plan"]
print(f"plan: {len(PLAN)} people -> {len(PLAN)} persons + {len(PLAN)} leads")
if not a.live:
    for p in PLAN[:5]:
        print(f"  {p['full_name']!r} ({p['company']}) -> {p['lead_title'][:64]!r}")
    print("\n--live not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
created, skipped, failed = [], [], []
print("\n=== WRITING ===")
for i, p in enumerate(PLAN, 1):
    email = p["email"]
    # GUARD 1 - has someone created this person (and a lead) since the map?
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(email)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    if pid:
        leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
        if any(not l.get("is_archived") for l in leads):
            skipped.append({"email": email, "why": "lead now exists", "person_id": pid})
            continue
        # GUARD 2 - open deal
        dl = (pd(f"/api/v2/deals?person_id={pid}&status=open&limit=5") or {}).get("data") or []
        if dl:
            skipped.append({"email": email, "why": f"open deal {dl[0].get('id')}",
                            "person_id": pid})
            continue
    # GUARD 3 - provider name required
    first, last = (p.get("first") or "").strip(), (p.get("last") or "").strip()
    if not (first and last):
        skipped.append({"email": email, "why": "no provider name"})
        continue

    if not pid:
        cf = {}
        if p.get("company"):
            cf[F_COMPANY] = p["company"]
        cf[F_CAMPAIGN] = p["campaign"]
        pb = {"first_name": first, "last_name": last, "owner_id": NOAH,
              "custom_fields": cf,
              "emails": [{"value": email, "primary": True, "label": "work"}]}
        rp = pd("/api/v2/persons", "POST", pb)
        pid = ((rp.get("data") or {}) or {}).get("id")
        if not pid:
            failed.append({"email": email, "stage": "person", "err": rp.get("__err")})
            continue
    lb = {"title": p["lead_title"], "person_id": pid, "owner_id": NOAH,
          "label_ids": [COLD], "channel": CHANNEL,
          F_LEADCAMP: p["campaign"], F_OPP: OPP_VALUE}
    rl = pd("/v1/leads", "POST", lb)
    lid = ((rl.get("data") or {}) or {}).get("id")
    if not lid:
        failed.append({"email": email, "stage": "lead", "person_id": pid,
                       "err": rl.get("__err")})
        continue
    created.append({"email": email, "person_id": pid, "lead_id": lid,
                    "name": f"{first} {last}"})
    print(f"  [{i}/{len(PLAN)}] {first} {last:<16} person {pid}  lead {str(lid)[:8]}")
    time.sleep(0.4)

print(f"\nCREATED {len(created)}   skipped {len(skipped)}   failed {len(failed)}")
for s_ in skipped:
    print(f"   SKIP {s_}")
for f_ in failed:
    print(f"   FAIL {f_}")

# ---- verification: re-derive the class, do not re-read the plan
print("\n--- verification (class re-derived) ---")
still = []
for p in PLAN:
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(p['email'])}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    if not pid:
        still.append({"email": p["email"], "why": "no person"})
        continue
    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
    if not any(not l.get("is_archived") for l in leads):
        still.append({"email": p["email"], "why": "still no lead", "person_id": pid})
print(f"  Finovate SENT-but-no-lead remaining: {len(still)}")
for s_ in still[:5]:
    print(f"     {s_}")
# and confirm the created leads are LINKED (the orphan class must not reappear)
orph = [c for c in created
        if not ((pd(f"/v1/leads/{c['lead_id']}") or {}).get("data") or {}).get("person_id")]
print(f"  newly created leads that are ORPHANED: {len(orph)}")
json.dump({"created": created, "skipped": skipped, "failed": failed, "still": still,
           "orphaned": orph},
          open(os.path.join(HERE, f"finovate_backfill_result_{stamp}.json"), "w",
               encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"\nresult: finovate_backfill_result_{stamp}.json")
