import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

r = requests.post(B + "/campaign/GetAll", headers=h, json={"offset": 0, "limit": 20}, timeout=30)
data = r.json()
for c in data.get("items", []):
    if c["id"] in (512995, 513000):
        print(json.dumps(c, indent=2, default=str)[:1500])
        print("---")

for cid, name in [(512995, "Mario"), (513000, "Rune")]:
    r2 = requests.post(B + "/campaign/GetLeadsFromCampaign", headers=h,
                       json={"campaignId": cid, "offset": 0, "limit": 1}, timeout=30)
    d2 = r2.json()
    print(name, cid, "GetLeadsFromCampaign totalCount:", d2.get("totalCount"))
