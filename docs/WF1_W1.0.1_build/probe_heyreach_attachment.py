#!/usr/bin/env python3
"""READ ONLY against HeyReach. The webhook carries no attachment marker - does the INBOX API?

The complete union of every leaf in all three Heath executions gives exactly three message fields:
creation_time, is_reply, message. No message_type, no attachments, no media, no content_type. So
`M7 Build.render()`'s '[attachment]' branch reads `m.message_type`, a key this webhook has never
sent, and an attachment-only reply is byte-identical to a truly empty one.

If the gate is ever to come back, the marker has to come from somewhere else. This asks the inbox
API whether it exposes one for this exact conversation.
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

HR = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://api.heyreach.io/api/public"
CONV = "2-YTdkNzM0NzctM2ZmYy00MTc2LWEwNzYtY2YzYjNmMWI4MGIzXzEwMA=="
PROFILE = "https://www.linkedin.com/in/pii-bffa9d4c"


def hr(path, body=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-API-KEY": HR, "Content-Type": "application/json",
                                        "Accept": "application/json", "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode("utf-8", "replace")
    except Exception as e:
        return "ERR", str(e)[:200]


def walk(o, prefix=""):
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            out += walk(v, prefix + "." + k if prefix else k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            out += walk(v, "%s[%d]" % (prefix, i))
    else:
        out.append((prefix, o))
    return out


print("=== GetConversationsV2, filtered to Heath's conversation ===")
for body in (
    {"filters": {"linkedInAccountIds": [], "campaignIds": [572715],
                 "searchString": "Tarbert"}, "offset": 0, "limit": 5},
    {"filters": {"searchString": "Tarbert"}, "offset": 0, "limit": 5},
):
    st, res = hr("/inbox/GetConversationsV2", body)
    print("\n  request: %s" % json.dumps(body)[:120])
    print("  -> HTTP %s" % st)
    if st != 200 or not isinstance(res, dict):
        print("     %s" % str(res)[:300])
        continue
    items = res.get("items") or res.get("conversations") or []
    print("     conversations returned: %d" % len(items))
    for c in items[:2]:
        cid = c.get("id") or c.get("conversationId") or c.get("groupId")
        print("     conversation id=%r" % str(cid)[:60])
        msgs = c.get("messages") or []
        print("     messages: %d" % len(msgs))
        for m in msgs[-4:]:
            print("       keys=%s" % sorted(m.keys()))
            print("       %s" % json.dumps(m, ensure_ascii=False)[:420])
    if items:
        print("\n  --- every leaf path of the first conversation ---")
        for p, v in walk(items[0]):
            s = repr(v)
            print("     %-52s = %s" % (p, s[:90]))
        hits = [p for p, _ in walk(items[0])
                if any(t in p.lower() for t in ("attach", "media", "file", "image", "type",
                                                "content", "kind"))]
        print("\n  attachment-ish paths: %s" % (hits or "NONE"))
        with open(os.path.join(HERE, "heyreach_conversation_probe.json"), "w",
                  encoding="utf-8") as f:
            json.dump(items[0], f, ensure_ascii=False, indent=1)
        print("  -> heyreach_conversation_probe.json")
        sys.exit(0)

print("\nNo conversation returned by either filter shape.")
