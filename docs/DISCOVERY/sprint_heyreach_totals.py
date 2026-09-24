import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

for cid, name in [(512995, "Mario-LinkedIn"), (513000, "Rune-LinkedIn")]:
    r = requests.post(B + "/campaign/GetById", headers=h, json={"campaignId": cid}, timeout=30)
    print(name, cid, "GetById status:", r.status_code, "-> keys:", list(r.json().keys()) if r.ok else r.text[:200])
    if r.ok:
        c = r.json()
        print("   ", {k: c.get(k) for k in ("id","name","status") if k in c})

# try to find lead-count endpoints
for path in ["/campaign/GetLeadsFromCampaign", "/campaign/GetCampaignAccountStats", "/leads/GetLeadStatistics", "/campaign/GetAll"]:
    try:
        r = requests.post(B + path, headers=h, json={"campaignId": 512995, "offset": 0, "limit": 1}, timeout=30)
        print(path, "->", r.status_code, r.text[:300])
    except Exception as e:
        print(path, "ERR", e)
