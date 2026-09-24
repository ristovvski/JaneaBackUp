import os, json, time, requests
K = os.environ["HEYREACH_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
HB = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

print("=== ALL HeyReach campaigns (account-wide) ===")
r = requests.post(HB + "/campaign/GetAll", headers=h, json={"offset": 0, "limit": 50}, timeout=45)
for c in r.json().get("items", []):
    pu = (c.get("progressStats") or {}).get("totalUsers")
    print(f"  {c['id']:>8}  status={c.get('status'):12s} totalUsers={pu}  name={c.get('name')!r}")

print("\n=== ALL Smartlead campaigns with 'ai4' in the name (any status) ===")
def sl(path, params=None):
    import urllib.parse
    q = dict(params or {}); q["api_key"] = SLK
    r = requests.get(f"https://server.smartlead.ai/api/v1{path}", params=q, timeout=45)
    return r.json()
camps = sl("/campaigns")
ai4 = [c for c in camps if "ai4" in (c.get("name") or "").lower()]
print(f"total campaigns account-wide: {len(camps)} | ai4-named: {len(ai4)}")
total_sl = 0
for c in ai4:
    st, cid = c.get("status"), c.get("id")
    d = sl(f"/campaigns/{cid}/leads", {"offset": 0, "limit": 1})
    n = int(d.get("total_leads") or 0) if isinstance(d, dict) else 0
    total_sl += n
    print(f"  {cid:>8}  status={st:10s} total_leads={n:5d}  name={c.get('name')!r}")
    time.sleep(0.1)
print(f"\nTOTAL Smartlead leads across ALL ai4-named campaigns: {total_sl}")
