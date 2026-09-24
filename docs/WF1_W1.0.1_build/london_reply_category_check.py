import os, json, requests, urllib.parse
SLK = os.environ["SMARTLEAD_API_KEY"]
def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    r = requests.get(f"https://server.smartlead.ai/api/v1{path}", params=q, timeout=45)
    return r.json()

cats = sl("/leads/fetch-categories")
cat_by_id = {c["id"]: c["name"] for c in cats}
print("categories:", cat_by_id)

d = json.load(open("../DISCOVERY/london_backfill_dryrun_output.json", encoding="utf-8"))
with_reply = [r for r in d["rows"] if r.get("has_reply")]
print(f"\n{len(with_reply)} reply rows - checking real Smartlead lead_category for each:")

CAMPS = {3565651: "Catch-alls", 3565502: "Valids"}
for r in with_reply:
    cid = r["campaign_id"]
    # find via /campaigns/{id}/leads (has lead_category_id)
    offset = 0
    found = None
    while found is None:
        page = sl(f"/campaigns/{cid}/leads", {"offset": offset, "limit": 100})
        data = page.get("data") or []
        for row in data:
            if (row.get("lead") or {}).get("email") == r["email"]:
                found = row
                break
        if found is not None or len(data) < 100:
            break
        offset += 100
    cat_id = found.get("lead_category_id") if found else None
    cat_name = cat_by_id.get(cat_id, "UNCATEGORIZED" if cat_id is None else f"unknown id {cat_id}")
    note_preview = r.get("reply_activity_body", {}).get("note", "")[:60]
    print(f"  {r['email']:40s} category={cat_name:25s} note_preview={note_preview!r}")
