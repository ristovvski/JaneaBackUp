import os, json, urllib.request, urllib.parse
SLK = os.environ["SMARTLEAD_API_KEY"]
UA = "Mozilla/5.0 janea-forensics/1.0"
def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    r = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=60) as x:
        return json.load(x)

CAMPS = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids", 3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
total = 0
for cid, name in CAMPS.items():
    d = sl(f"/campaigns/{cid}/leads", {"offset": 0, "limit": 1})
    n = int(d.get("total_leads") or 0)
    print(f"  {name} ({cid}): total_leads = {n}")
    total += n
print(f"\nTOTAL email leads across 4 campaigns (total_leads field): {total}")

# also check campaign status/name to confirm these 4 really are "the sprint" and not a subset
for cid in CAMPS:
    c = sl(f"/campaigns/{cid}")
    print(f"  campaign {cid}: name={c.get('name')!r} status={c.get('status')!r} created_at={c.get('created_at')}")
