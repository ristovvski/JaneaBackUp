#!/usr/bin/env python3
"""215-name repair, STEP 1 — build the rename map as an artifact. READ ONLY.

The London backfill wrote `name = email.split("@")[0]` for 215 persons and used the same string in
the lead title. Smartlead held the real first/last/company all along.

For each of the 215 emails this resolves:
    Pipedrive  person id + CURRENT name (+ its lead id and title)
    Smartlead  first_name / last_name / company_name
and emits old -> new, with an explicit skip reason wherever a rename must NOT happen.

THE GUARD, applied here and re-applied at write time: only touch a record whose person name STILL
equals the email local-part. If someone has since corrected it by hand, or the name never matched
the pattern, we leave it alone. A repair that overwrites human edits is worse than the bug.

Writes name_repair_map.json. No mutations.
"""
import hashlib, json, os, re, ssl, urllib.parse, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "DISCOVERY",
                   "london_backfill_dryrun_v2_output.json")


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


d = json.load(open(SRC, encoding="utf-8"))
rows = d.get("rows") if isinstance(d, dict) else d
if isinstance(d, dict) and not rows:
    for v in d.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "person_body" in v[0]:
            rows = v
            break
print(f"source rows: {len(rows)}")

out = []
skips = {}
for i, r in enumerate(rows, 1):
    email = str(r.get("email") or "").strip()
    if not email:
        skips["no_email"] = skips.get("no_email", 0) + 1
        continue
    local = email.split("@")[0]

    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(email)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    if not items:
        skips["person_not_found"] = skips.get("person_not_found", 0) + 1
        continue
    person = items[0].get("item") or {}
    pid = person.get("id")
    cur_name = str(person.get("name") or "")

    # THE GUARD
    if cur_name != local:
        skips["name_already_changed"] = skips.get("name_already_changed", 0) + 1
        continue

    prov = sl("/leads/", email=email)
    if not isinstance(prov, dict) or prov.get("__err"):
        skips["smartlead_lookup_failed"] = skips.get("smartlead_lookup_failed", 0) + 1
        continue
    first = str(prov.get("first_name") or "").strip()
    last = str(prov.get("last_name") or "").strip()
    company = str(prov.get("company_name") or "").strip()
    new_name = " ".join([x for x in (first, last) if x]).strip()
    if not new_name:
        skips["provider_has_no_name"] = skips.get("provider_has_no_name", 0) + 1
        continue
    if new_name == cur_name:
        skips["already_correct"] = skips.get("already_correct", 0) + 1
        continue

    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
    lead_edits = []
    for l in leads:
        t = str(l.get("title") or "")
        if t.endswith(" - " + local):
            lead_edits.append({"lead_id": l.get("id"), "old_title": t,
                               "new_title": t[: -len(local)] + new_name})
    out.append({"email": email, "person_id": pid, "local_part": local,
                "old_name": cur_name, "new_name": new_name,
                "first_name": first, "last_name": last, "company_name": company,
                "leads": lead_edits})
    if i % 25 == 0:
        print(f"  ...{i}/{len(rows)} processed, {len(out)} renameable")

print(f"\nRENAMEABLE: {len(out)} persons, {sum(len(x['leads']) for x in out)} lead titles")
print("skips:", json.dumps(skips, indent=1))
miss_company = [x for x in out if not x["company_name"]]
print(f"  of those, without a provider company: {len(miss_company)}")
print("\nsample:")
for x in out[:8]:
    print(f"  {x['email']:<38} {x['old_name']!r} -> {x['new_name']!r}  "
          f"({x['company_name'] or 'no company'})  leads={len(x['leads'])}")
json.dump({"renameable": out, "skips": skips}, open(
    os.path.join(HERE, "name_repair_map.json"), "w", encoding="utf-8"),
    indent=1, ensure_ascii=False)
print(f"\nartifact: name_repair_map.json")
