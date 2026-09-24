#!/usr/bin/env python3
"""Verify the ACTUAL query shape of Pipedrive's archived-visible search routes before building
the real enumeration -- do they support filtering by label_ids server-side, or only a text
'term'? Test against the known-archived positive control (lead 5050e6a0..., person 70255) from
the prior audit doc, and check what fields the response actually carries (label_ids present?)."""
import json, os, ssl, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else ssl.create_default_context()
RESPONDED_LABEL = "c9d4b550-bcf3-11ef-a843-357f91e826ec"


def pd_get(url, params):
    import urllib.parse
    params = dict(params)
    params["api_token"] = PD_TOKEN
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers={"accept": "application/json",
                                                           "User-Agent": "Mozilla/5.0 janea-archived/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("=== 1. v1/leads/search with a broad common term, check response shape ===")
status, body = pd_get("https://api.pipedrive.com/v1/leads/search", {"term": "a", "limit": 5})
print("status", status)
print(json.dumps(body, indent=2)[:2000])

print("\n=== 2. v1/itemSearch item_types=lead, same term ===")
status, body = pd_get("https://api.pipedrive.com/v1/itemSearch", {"term": "a", "item_types": "lead", "limit": 5})
print("status", status)
print(json.dumps(body, indent=2)[:2000])

print("\n=== 3. api/v2/leads/search ===")
status, body = pd_get("https://api.pipedrive.com/api/v2/leads/search", {"term": "a", "limit": 5})
print("status", status)
print(json.dumps(body, indent=2)[:2000])

print("\n=== 4. does v1/leads/search accept a filter_id or label param? try common param names ===")
for extra_param in ["filter_id", "label", "label_ids"]:
    status, body = pd_get("https://api.pipedrive.com/v1/leads/search", {"term": "a", extra_param: "1"})
    print(f"  with {extra_param}: status={status} success={body.get('success')}")
