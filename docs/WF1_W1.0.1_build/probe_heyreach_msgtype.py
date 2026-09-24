#!/usr/bin/env python3
"""READ ONLY. `lastMessageType` is the only candidate marker left - does it EVER say anything but
TEXT?

For Heath's conversation the inbox API reports `lastMessageType: 'TEXT'`, `body: ''`,
`isVoiceNote: false`, `transcript: null`, `postLink: null` - while the HeyReach UI shows
"Attachment(s)". If the field is TEXT for every conversation in the account, it carries no
information and there is no marker anywhere in the API surface.
"""
import json
import os
import ssl
import urllib.request
from collections import Counter

HR = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
BASE = "https://api.heyreach.io/api/public"


def hr(path, body):
    r = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode(),
                               headers={"X-API-KEY": HR, "Content-Type": "application/json",
                                        "Accept": "application/json", "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)[:200]


types, empties, msgkeys = Counter(), 0, Counter()
total, offset = 0, 0
for _ in range(6):
    st, res = hr("/inbox/GetConversationsV2",
                 {"filters": {}, "offset": offset, "limit": 100})
    if st != 200 or not isinstance(res, dict):
        print("HTTP %s %s" % (st, str(res)[:200]))
        break
    items = res.get("items") or []
    if not items:
        break
    for c in items:
        total += 1
        types[str(c.get("lastMessageType"))] += 1
        if not str(c.get("lastMessageText") or "").strip():
            empties += 1
        for m in (c.get("messages") or []):
            msgkeys.update(m.keys())
    offset += len(items)
    if len(items) < 100:
        break

print("conversations sampled: %d" % total)
print("\nlastMessageType values:")
for k, v in types.most_common():
    print("   %-16s %d" % (k, v))
print("\nconversations whose last message text is EMPTY: %d" % empties)
print("\nunion of message-object keys across every sampled message:")
print("   %s" % sorted(msgkeys))
cand = [k for k in msgkeys if any(t in k.lower()
                                  for t in ("attach", "media", "file", "image", "type", "kind"))]
print("\nattachment-ish message keys: %s" % (cand or "NONE"))
