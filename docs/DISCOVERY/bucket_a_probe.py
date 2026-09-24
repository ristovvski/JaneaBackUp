import os, json, requests, urllib.parse, random
SLK = os.environ["SMARTLEAD_API_KEY"]
def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    r = requests.get(f"https://server.smartlead.ai/api/v1{path}", params=q, timeout=45)
    return r.json()

CAMPS = {3565651: "London-Catch-alls", 3565502: "London-Valids"}

# 1) get the set of emails that DID appear in leads-statistics (already pulled)
stats_emails = set()
for cid in CAMPS:
    skip = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        data = page.get("data") or []
        for row in data:
            if row.get("to"):
                stats_emails.add(row["to"].lower())
        if not page.get("hasMore"):
            break
        skip += 100

print(f"unique emails seen in leads-statistics: {len(stats_emails)}")

# 2) pull the full campaign lead list via a different endpoint (/campaigns/{id}/leads), which should
#    include ALL uploaded leads regardless of send status
all_leads = []
for cid, name in CAMPS.items():
    offset = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads", {"offset": offset, "limit": 100})
        rows = page.get("data") if isinstance(page, dict) else page
        if not rows:
            break
        for r in rows:
            lead = r.get("lead") or r
            email = (lead.get("email") or "").lower()
            all_leads.append({"campaign": name, "email": email,
                               "status": r.get("lead_category_id") or r.get("status") or lead.get("status"),
                               "raw_status_field": {k: r.get(k) for k in r if "status" in k.lower() or "category" in k.lower()}})
        if len(rows) < 100:
            break
        offset += 100

print(f"total rows via /campaigns/{{id}}/leads: {len(all_leads)}")
empty_email = sum(1 for l in all_leads if not l["email"])
print(f"rows with empty/missing email: {empty_email}")
distinct_emails = set(l["email"] for l in all_leads if l["email"])
print(f"distinct non-empty emails in /leads pull: {len(distinct_emails)}")
dupe_rows = len(all_leads) - empty_email - len(distinct_emails)
print(f"duplicate rows (same email appearing >1x within /leads pull): {dupe_rows}")
absent = [l for l in all_leads if l["email"] and l["email"] not in stats_emails]
print(f"absent from leads-statistics but present in /leads list (row-level, may double count dupes): {len(absent)}")
absent_distinct = set(l["email"] for l in absent)
print(f"absent, DISTINCT emails: {len(absent_distinct)}")

sample = random.sample(absent, min(20, len(absent))) if absent else []
for a in sample:
    print(" ", a["email"], "|", a["campaign"], "| status_fields:", a["raw_status_field"])
