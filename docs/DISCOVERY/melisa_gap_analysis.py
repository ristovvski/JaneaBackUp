#!/usr/bin/env python3
"""READ-ONLY. Melisa's ask: 372 Ai4 leads missing "Event name" / "Marketing Hypothesis" on the
linked person (confirmed: these fields exist ONLY on the person object, not on leads at all).

Step A: pull ALL leads (paginated, sort=add_time DESC per the ordering-trap rule, archived_status=
        all), keep any whose TITLE mentions "ai4" (case-insensitive) OR whose lead Campaign field
        mentions "ai4" -- title match is load-bearing: Make leaves the lead Campaign field EMPTY
        (wf2-b24-duplicate-leads), so campaign-field-only matching would silently miss every
        Make-created Ai4 lead.
Step B: pull ALL persons (paginated, same proven pattern as c2_backfill300_refresh.py), capturing
        id, email, add_time, owner_id, and the two target field values.
Step C: join leads -> person via person_id, bucket has/missing for each field.
Step D: for a sample of each bucket, pull the person's changelog to get creation actor + user_agent
        (attribution) and, for the HAS bucket, the actual field-write actor/value (ground truth).
No writes anywhere.
"""
import json, os, ssl, time
import urllib.request, urllib.parse
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))
F_EVENT = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"


def pd(path, params=None, tries=4):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


# ---- Step A: all Ai4 leads ----
print("Step A: pulling all leads (sort=add_time DESC, archived_status=all)...")
leads = []
start = 0
while True:
    page = pd("/leads", {"start": start, "limit": 500, "sort": "add_time DESC", "archived_status": "all"})
    if "__err" in page:
        print("  ERROR:", page); break
    rows = page.get("data") or []
    if not rows:
        break
    leads.extend(rows)
    ad = (page.get("additional_data") or {}).get("pagination") or {}
    if not ad.get("more_items_in_collection"):
        break
    start = ad.get("next_start") or (start + len(rows))
    if len(leads) % 2000 == 0:
        print(f"  ...{len(leads)} leads so far")
print(f"  total leads in account: {len(leads)}")

def is_ai4(ld):
    title = (ld.get("title") or "").lower()
    camp = str(ld.get(F_LEADCAMP) or "").lower()
    return "ai4" in title or "ai4" in camp

ai4_leads = [l for l in leads if is_ai4(l)]
print(f"  Ai4-matching leads: {len(ai4_leads)} (title match: {sum(1 for l in ai4_leads if 'ai4' in (l.get('title') or '').lower())}, "
      f"campaign-field-only match: {sum(1 for l in ai4_leads if 'ai4' not in (l.get('title') or '').lower() and 'ai4' in str(l.get(F_LEADCAMP) or '').lower())})")

with open(os.path.join(HERE, "melisa_ai4_leads_raw.jsonl"), "w", encoding="utf-8") as f:
    for l in ai4_leads:
        f.write(json.dumps(l, default=str) + "\n")

# ---- Step B: all persons, capturing the two target fields ----
print("\nStep B: pulling all persons (this takes a while, ~114 pages)...")
persons_by_id = {}
start = 0
pages = 0
while True:
    page = pd("/persons", {"start": start, "limit": 500, "sort": "add_time DESC"})
    if "__err" in page:
        print("  ERROR:", page); break
    rows = page.get("data") or []
    if not rows:
        break
    for p in rows:
        persons_by_id[p["id"]] = {
            "id": p["id"], "email": (p.get("email") or [{}])[0].get("value") if isinstance(p.get("email"), list) else p.get("email"),
            "add_time": p.get("add_time"), "owner_id": (p.get("owner_id") or {}).get("value") if isinstance(p.get("owner_id"), dict) else p.get("owner_id"),
            "event_name": p.get(F_EVENT), "hypothesis": p.get(F_HYPO),
        }
    pages += 1
    ad = (page.get("additional_data") or {}).get("pagination") or {}
    if not ad.get("more_items_in_collection"):
        break
    start = ad.get("next_start") or (start + len(rows))
    if pages % 20 == 0:
        print(f"  ...{pages} pages, {len(persons_by_id)} persons so far")
print(f"  total persons scanned: {pages} pages, {len(persons_by_id)} persons")

with open(os.path.join(HERE, "melisa_persons_fields.json"), "w", encoding="utf-8") as f:
    json.dump(persons_by_id, f, default=str)

# ---- Step C: join + bucket ----
print("\nStep C: joining leads -> persons, bucketing has/missing...")
def empty(v):
    return v is None or str(v).strip() == ""

buckets = {"event_has": [], "event_missing": [], "hypo_has": [], "hypo_missing": [], "person_not_found": []}
joined = []
for ld in ai4_leads:
    pid = ld.get("person_id")
    if isinstance(pid, dict):
        pid = pid.get("value")
    p = persons_by_id.get(pid)
    rec = {"lead_id": ld["id"], "title": ld.get("title"), "person_id": pid,
           "campaign_field": ld.get(F_LEADCAMP), "lead_add_time": ld.get("add_time")}
    if p is None:
        buckets["person_not_found"].append(rec)
        joined.append({**rec, "event_name": None, "hypothesis": None, "person_found": False})
        continue
    rec["event_name"] = p["event_name"]; rec["hypothesis"] = p["hypothesis"]
    rec["person_email"] = p["email"]; rec["person_add_time"] = p["add_time"]; rec["person_owner_id"] = p["owner_id"]
    (buckets["event_missing"] if empty(p["event_name"]) else buckets["event_has"]).append(rec)
    (buckets["hypo_missing"] if empty(p["hypothesis"]) else buckets["hypo_has"]).append(rec)
    joined.append({**rec, "person_found": True})

print(f"\n  Ai4 leads total: {len(ai4_leads)}")
print(f"  Event name  -> HAS: {len(buckets['event_has'])}  MISSING: {len(buckets['event_missing'])}")
print(f"  Hypothesis  -> HAS: {len(buckets['hypo_has'])}  MISSING: {len(buckets['hypo_missing'])}")
print(f"  person_id not resolvable to a person record: {len(buckets['person_not_found'])}")

with open(os.path.join(HERE, "melisa_gap_joined.json"), "w", encoding="utf-8") as f:
    json.dump({"buckets": {k: v for k, v in buckets.items()}, "all": joined}, f, indent=2, default=str)

print("\nwrote melisa_ai4_leads_raw.jsonl, melisa_persons_fields.json, melisa_gap_joined.json")
