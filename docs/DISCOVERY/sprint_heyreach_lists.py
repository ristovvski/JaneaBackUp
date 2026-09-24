import os, json, requests
K = os.environ["HEYREACH_API_KEY"]
B = "https://api.heyreach.io/api/public"
h = {"X-API-KEY": K, "accept": "application/json", "Content-Type": "application/json"}

for path, body in [
    ("/list/GetAll", {"offset": 0, "limit": 20}),
    ("/list/GetById", {"listId": 803602}),
    ("/list/GetById", {"listId": 803592}),
]:
    try:
        r = requests.post(B + path, headers=h, json=body, timeout=30)
        print(path, body, "->", r.status_code, r.text[:500])
    except Exception as e:
        print(path, "ERR", e)
