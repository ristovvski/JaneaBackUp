#!/usr/bin/env python3
"""Register the real, permanent Pipedrive webhook subscriptions (lead + person, all actions)
pointed at the production dnc_i04_event_receiver. Run once; prints the subscription ids for the
record (needed later if they ever need deleting/rotating)."""
import json, os, ssl, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
PD_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
RECEIVER_URL = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_I04_PD_EVENTS}}"


def register(event_object):
    body = json.dumps({"subscription_url": RECEIVER_URL, "event_action": "*", "event_object": event_object}).encode()
    req = urllib.request.Request(f"https://api.pipedrive.com/v1/webhooks?api_token={PD_TOKEN}",
                                  method="POST", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            result = json.loads(r.read())
        data = result.get("data", {})
        print(f"{event_object}: registered id={data.get('id')} is_active={data.get('is_active')} version={data.get('version')}")
        return data.get("id")
    except urllib.error.HTTPError as e:
        print(f"{event_object}: FAILED", e.code, e.read()[:500])
        return None


if __name__ == "__main__":
    print("subscription_url:", RECEIVER_URL)
    ids = {"lead": register("lead"), "person": register("person")}
    print(json.dumps(ids, indent=2))
