#!/usr/bin/env python3
"""§9f.2 artifact — repair today's damage: relink orphaned Finovate leads + rename email-named
persons. READ ONLY, writes name_orphan_repair_map.json.

The only link between an orphaned lead and its person is the EXECUTION that created it: the lead
carries no email and (because full_name was null) no name in its title either. So the map is built
from execution history — `Lead Create` response id -> that run's `Person Id Final.__person_id` and
Normalize email — then names come from Smartlead by that email.

Nothing here depends on the new plumbing; it reads historical runs.
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


# ---- 1. every lead WF-2 created, from execution history: lead_id -> (person_id, email)
print("walking WF-2 executions for Lead Create results...")
created = {}
cur, pages = None, 0
while pages < 8:
    q = {"workflowId": "jp7rum9Z0YDJkQWv", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "Lead Create" not in rd:
            continue

        def o(nm):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"]
            except Exception:
                return None

        lc = o("Lead Create") or {}
        lid = ((lc.get("data") or {}) or {}).get("id")
        if not lid:
            continue
        pidj = o("Person Id Final") or o("Carry Person Ctx") or {}
        nz = o("Normalize") or {}
        created[lid] = {"exec": r["id"], "at": r.get("startedAt"),
                        "person_id": pidj.get("__person_id"),
                        "email": (nz.get("lead") or {}).get("email"),
                        "campaign": nz.get("campaign_name")}
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break
print(f"  leads created by WF-2 in retained history: {len(created)}")

# ---- 2. the orphans, live
print("\nscanning Pipedrive for orphaned Finovate leads...")
orphans, start = [], 0
while start < 600:
    r = pd(f"/v1/leads?limit=100&start={start}&sort=add_time%20DESC")
    rows = (r or {}).get("data") or []
    if not rows:
        break
    for x in rows:
        t = str(x.get("title") or "")
        if (t.startswith("3868449 - ") or t.startswith("3868450 - ")) and not x.get("person_id"):
            orphans.append(x)
    more = ((r.get("additional_data") or {}).get("pagination") or {})
    if not more.get("more_items_in_collection"):
        break
    start = more.get("next_start") or (start + 100)
print(f"  orphaned Finovate leads: {len(orphans)}")

# ---- 3. build the repair plan
plan, unmatched = [], []
for l in orphans:
    lid = l.get("id")
    src = created.get(lid)
    if not src or not src.get("person_id"):
        unmatched.append({"lead_id": lid, "why": "no creating execution retained / no person id"})
        continue
    email = src.get("email")
    prov = sl("/leads/", email=email) if email else {}
    first = str((prov or {}).get("first_name") or "").strip()
    last = str((prov or {}).get("last_name") or "").strip()
    p = (pd(f"/api/v2/persons/{src['person_id']}") or {}).get("data") or {}
    cur_name = str(p.get("name") or "")
    needs_rename = bool(first and last) and cur_name == email
    plan.append({"lead_id": lid, "person_id": src["person_id"], "email": email,
                 "exec": src["exec"], "campaign": src.get("campaign"),
                 "person_name_now": cur_name,
                 "first": first, "last": last,
                 "needs_rename": needs_rename,
                 "lead_title": str(l.get("title"))[:70]})

print(f"\nRELINKABLE          : {len(plan)}")
print(f"  of those, person also needs renaming from email: "
      f"{sum(1 for x in plan if x['needs_rename'])}")
print(f"UNMATCHED (left alone): {len(unmatched)}")
for u in unmatched[:5]:
    print(f"   {u}")

print("\n--- 5 example rows (old -> new) ---")
for x in plan[:5]:
    print(f"  lead {str(x['lead_id'])[:8]}  person_id: None -> {x['person_id']}")
    print(f"     person {x['person_id']}: {x['person_name_now']!r} -> "
          f"{(x['first'] + ' ' + x['last']) if x['needs_rename'] else '(name already fine)'}")

json.dump({"plan": plan, "unmatched": unmatched},
          open(os.path.join(HERE, "orphan_repair_map.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"\nartifact: orphan_repair_map.json")
