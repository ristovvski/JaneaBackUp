import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

print("=== probe 1: empty body (elicit validation error) ===")
r = requests.post(B + "/inbox/GetConversationsV2", headers=h, json={}, timeout=30)
print(r.status_code, r.text[:800])

print("\n=== probe 2: alternate path guesses (checking which exists at all) ===")
for path in ["/GetConversationsV2", "/conversation/GetConversationsV2", "/li_conversation/GetConversationsV2"]:
    try:
        r2 = requests.post(B + path, headers=h, json={}, timeout=20)
        print(path, "->", r2.status_code, r2.text[:200])
    except Exception as e:
        print(path, "ERR", str(e)[:150])
