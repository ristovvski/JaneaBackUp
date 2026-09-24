import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}
CONV_ID = "2-YWU3MTVjOTUtNDZhZC00NTk0LWFjYmYtOTkxODY1Yzk1NjUyXzEwMA=="

# full first item, unabbreviated
r = requests.post(B + "/inbox/GetConversationsV2", headers=h, json={}, timeout=30)
d = r.json()
first = d["items"][0]
print("first item full keys:", list(first.keys()))
print(json.dumps(first, indent=2, default=str))

print("\n=== try passing conversationId / filters to GetConversationsV2 itself ===")
for body in (
    {"conversationId": CONV_ID},
    {"filters": {"conversationId": CONV_ID}},
    {"linkedInAccountId": 226601, "correspondentProfileId": "778402452"},
):
    r2 = requests.post(B + "/inbox/GetConversationsV2", headers=h, json=body, timeout=30)
    print(body, "->", r2.status_code, r2.text[:400])
