import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}
CONV_ID = "2-YWU3MTVjOTUtNDZhZC00NTk0LWFjYmYtOTkxODY1Yzk1NjUyXzEwMA=="

candidates = [
    ("/inbox/GetChatroomMessages", {"conversationId": CONV_ID}),
    ("/inbox/GetChatroomMessagesV2", {"conversationId": CONV_ID}),
    ("/inbox/GetConversationMessages", {"conversationId": CONV_ID}),
    ("/inbox/GetConversationMessagesV2", {"conversationId": CONV_ID}),
    ("/inbox/GetMessages", {"conversationId": CONV_ID}),
]
for path, body in candidates:
    try:
        r = requests.post(B + path, headers=h, json=body, timeout=30)
        print(path, "->", r.status_code, r.text[:300])
    except Exception as e:
        print(path, "ERR", str(e)[:150])
