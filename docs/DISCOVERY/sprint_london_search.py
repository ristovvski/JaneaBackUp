import os, json, requests, urllib.parse
SLK = os.environ["SMARTLEAD_API_KEY"]
def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    r = requests.get(f"https://server.smartlead.ai/api/v1{path}", params=q, timeout=45)
    return r.json()

camps = sl("/campaigns")
print(f"total campaigns account-wide: {len(camps)}")
sprint = [c for c in camps if "sprint" in (c.get("name") or "").lower()]
print(f"'sprint' in name (any casing): {len(sprint)}")
total = 0
for c in sprint:
    cid = c["id"]
    d = sl(f"/campaigns/{cid}/leads", {"offset": 0, "limit": 1})
    n = int(d.get("total_leads") or 0) if isinstance(d, dict) else 0
    total += n
    print(f"  {cid:>8}  status={c.get('status'):10s} total_leads={n:5d}  created={c.get('created_at')}  name={c.get('name')!r}")
print(f"\nTOTAL leads across all 'sprint'-named campaigns: {total}")

london = [c for c in sprint if "london" in (c.get("name") or "").lower()]
print(f"\n'london' + 'sprint' in name: {len(london)}")
ltotal = 0
for c in london:
    cid = c["id"]
    d = sl(f"/campaigns/{cid}/leads", {"offset": 0, "limit": 1})
    n = int(d.get("total_leads") or 0) if isinstance(d, dict) else 0
    ltotal += n
    print(f"  {cid:>8}  status={c.get('status'):10s} total_leads={n:5d}  name={c.get('name')!r}")
print(f"\nTOTAL leads across London sprint campaigns: {ltotal}")
