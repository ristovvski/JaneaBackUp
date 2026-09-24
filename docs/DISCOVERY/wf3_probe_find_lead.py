import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

# Rune's LinkedIn campaign = 513000 per earlier discovery
cid = 513000
offset = 0
found = None
while found is None:
    r = requests.post(B + "/campaign/GetLeadsFromCampaign", headers=h,
                      json={"campaignId": cid, "offset": offset, "limit": 100}, timeout=45)
    d = r.json()
    items = d.get("items") or []
    if not items:
        break
    for it in items:
        prof = it.get("linkedInUserProfile") or {}
        name = ((prof.get("firstName") or "") + " " + (prof.get("lastName") or "")).strip()
        if "gillan" in name.lower() or "aneel" in name.lower():
            found = it
            break
    if len(items) < 100:
        break
    offset += 100

print("found:", json.dumps(found, indent=2, default=str)[:2500] if found else "NOT FOUND in campaign 513000")
