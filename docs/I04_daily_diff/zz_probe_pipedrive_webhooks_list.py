#!/usr/bin/env python3
"""Read-only: list any Pipedrive webhook subscriptions already registered on this account, before
designing the event-driven I-04 redesign. Also probe whether the v1 webhooks endpoint is reachable
with our existing token at all (subscription creation may need different scopes than read-only
projection calls)."""
import json, os, ssl, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]

for url in [
    f"https://api.pipedrive.com/v1/webhooks?api_token={PD_TOKEN}",
]:
    print("GET", url.split("?")[0])
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            body = json.loads(r.read())
            print(json.dumps(body, indent=2)[:3000])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read()[:1000])
    print()
