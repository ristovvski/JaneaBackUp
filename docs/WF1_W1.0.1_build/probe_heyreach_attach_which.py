#!/usr/bin/env python3
"""READ ONLY, and this is the deciding question.

600 conversations sampled: `lastMessageType` is ATTACHMENT for 3, and exactly 3 have an empty last
message text. Heath's conversation read as TEXT in the filtered query. So either

  (a) Heath IS one of the three -> the marker EXISTS in the inbox API and the filtered read that
      said TEXT was wrong or stale, or
  (b) Heath is NOT -> his empty message is something else again, and the UI's "Attachment(s)" comes
      from a surface the API does not expose.

Name the three. Print Heath's row from the unfiltered listing, not the filtered one.
"""
import json
import os
import ssl
import urllib.request

HR = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
BASE = "https://api.heyreach.io/api/public"
CONV = "2-YTdkNzM0NzctM2ZmYy00MTc2LWEwNzYtY2YzYjNmMWI4MGIzXzEwMA=="


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


attach, empty, heath = [], [], None
offset = 0
for _ in range(8):
    st, res = hr("/inbox/GetConversationsV2", {"filters": {}, "offset": offset, "limit": 100})
    if st != 200 or not isinstance(res, dict):
        print("HTTP %s %s" % (st, str(res)[:200]))
        break
    items = res.get("items") or []
    if not items:
        break
    for c in items:
        who = ((c.get("correspondentProfile") or {}).get("firstName") or "") + " " + \
              ((c.get("correspondentProfile") or {}).get("lastName") or "")
        row = {"id": str(c.get("id"))[:44], "who": who.strip(),
               "lastMessageType": c.get("lastMessageType"),
               "lastMessageText": str(c.get("lastMessageText") or "")[:40],
               "lastMessageSender": c.get("lastMessageSender"),
               "lastMessageAt": c.get("lastMessageAt"),
               "totalMessages": c.get("totalMessages")}
        if c.get("lastMessageType") == "ATTACHMENT":
            attach.append(row)
        if not str(c.get("lastMessageText") or "").strip():
            empty.append(row)
        if str(c.get("id")) == CONV:
            heath = dict(row)
            heath["messages"] = c.get("messages")
    offset += len(items)
    if len(items) < 100:
        break

print("=== conversations with lastMessageType == ATTACHMENT (%d) ===" % len(attach))
for r in attach:
    print("  %-44s %-22s sender=%-13s at=%s  msgs=%s"
          % (r["id"], r["who"][:22], r["lastMessageSender"], r["lastMessageAt"],
             r["totalMessages"]))

print("\n=== conversations whose last message text is EMPTY (%d) ===" % len(empty))
for r in empty:
    print("  %-44s %-22s type=%-11s sender=%-13s at=%s"
          % (r["id"], r["who"][:22], r["lastMessageType"], r["lastMessageSender"],
             r["lastMessageAt"]))

print("\n=== Heath's conversation, from the UNFILTERED listing ===")
if not heath:
    print("  NOT FOUND in the unfiltered pages walked - it may be beyond the pages sampled")
else:
    print("  lastMessageType   = %r" % heath["lastMessageType"])
    print("  lastMessageText   = %r" % heath["lastMessageText"])
    print("  lastMessageSender = %r" % heath["lastMessageSender"])
    print("  totalMessages     = %r" % heath["totalMessages"])
    for m in (heath.get("messages") or []):
        print("   msg %s" % json.dumps(m, ensure_ascii=False)[:300])
    print("\n  IS HEATH ONE OF THE ATTACHMENT THREE: %s"
          % ("YES" if heath["lastMessageType"] == "ATTACHMENT" else "NO"))
