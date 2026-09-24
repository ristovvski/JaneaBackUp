"""READ-ONLY reconciliation, mirroring the Ai4 backfill-300 methodology exactly: pull every
Smartlead lead EMAIL for the two named London 2026 campaigns, check each by EXACT email match
against Pipedrive persons (never by campaign-field string, which Make is known to corrupt/leave
empty). This is the rigorous version of bucket (b) - not a fragile field-string count.
"""
import json, os, ssl, time
import urllib.request, urllib.parse

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 janea-forensics/1.0"

CAMPS = {3565651: "London-2026-Catch-alls", 3565502: "London-2026-Valids"}


def sl(path, params=None, tries=4):
    q = dict(params or {}); q["api_key"] = SLK
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(4); continue
            return {"__err": str(e)[:200]}


def pd(path, params=None, tries=4):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


# 1) pull every lead (email + reply/category info) from both London campaigns via leads-statistics
rows = []
for cid, name in CAMPS.items():
    skip = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if "__err" in page:
            print(f"  ERROR {cid}: {page}"); break
        data = page.get("data") or []
        for row in data:
            email = row.get("to")
            replies = [h for h in (row.get("history") or []) if h.get("type") == "REPLY"]
            rows.append({"campaign": name, "campaign_id": cid, "email": email,
                         "has_reply": bool(replies), "reply_count": len(replies)})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.1)
print(f"total lead rows pulled from Smartlead (both campaigns): {len(rows)}")
unique_emails = len(set(r["email"] for r in rows if r["email"]))
print(f"unique emails: {unique_emails}")

# 2) check each by EXACT email match against Pipedrive persons
missing = []
found = 0
checked = 0
for r in rows:
    email = r["email"]
    if not email:
        continue
    s = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true", "limit": 1})
    items = ((s or {}).get("data") or {}).get("items") or []
    checked += 1
    if items:
        found += 1
    else:
        missing.append(r)
    if checked % 200 == 0:
        print(f"  ...checked {checked}/{len(rows)}, missing so far {len(missing)}")
    time.sleep(0.05)

print(f"\nchecked: {checked}  found_in_pipedrive: {found}  MISSING: {len(missing)}")
missing_with_reply = [m for m in missing if m["has_reply"]]
print(f"of the missing, has at least one REPLY event: {len(missing_with_reply)}")

with open(os.path.join(HERE, "sprint_london_missing.json"), "w", encoding="utf-8") as f:
    json.dump({"total_checked": checked, "found": found, "missing_count": len(missing),
                "missing": missing, "missing_with_reply": missing_with_reply}, f, indent=2, ensure_ascii=False)
print("wrote sprint_london_missing.json")
