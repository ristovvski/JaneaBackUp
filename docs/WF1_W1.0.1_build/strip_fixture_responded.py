#!/usr/bin/env python3
"""Remove '3. Responded' from the FLIP-GATE TEST lead only, so its next reply is a first reply
again and the converted Reply Alert can actually fire.

Scoped hard: refuses unless the lead is the known test fixture AND its title carries the TEST
marker. Removing a responded label from a real prospect would corrupt reporting.
"""
import json, os, ssl, sys, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NAMES = {"a6d359b0-6a45-11ed-ab46-5b95b19fcb18": "1. Cold",
         "ca698a50-bdfb-11ef-8172-510383583b0e": "2. Connected",
         "c9d4b550-bcf3-11ef-a843-357f91e826ec": "3. Responded"}


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea-fixture/1.0"})
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        return json.load(x)


L = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
title = str(L.get("title") or "")
print(f"lead  : {LEAD}")
print(f"title : {title}")
print(f"labels: {[NAMES.get(x, x) for x in (L.get('label_ids') or [])]}")

if "FLIP-GATE TEST" not in title.upper():
    print("REFUSING: this lead is not the test fixture - never strip a real prospect's label")
    sys.exit(2)

labels = [x for x in (L.get("label_ids") or []) if x != RESPONDED]
if labels == (L.get("label_ids") or []):
    print("'3. Responded' not present - nothing to strip")
    sys.exit(0)

r = pd(f"/v1/leads/{LEAD}", "PATCH", {"label_ids": labels})
back = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
now = back.get("label_ids") or []
ok = RESPONDED not in now
print(f"after : {[NAMES.get(x, x) for x in now]}")
print("STRIP", "CLEAN" if ok else "FAILED")
sys.exit(0 if ok else 1)
