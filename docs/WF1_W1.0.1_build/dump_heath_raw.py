#!/usr/bin/env python3
"""READ ONLY. Where does HeyReach signal an attachment?

Heath sent an attachment with no text at 03:34. My gate called it blank, and my attachment static
used `message_type: 'ATTACHMENT'` - a key I took from `M7 Build.render()`, not from the wire. So:
print the COMPLETE raw webhook body for both reply executions, every key at every depth, with
nothing filtered. Then compare against what render() actually reads.
"""
import json
import os
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        raise


def walk(o, prefix=""):
    """Every leaf path, so a marker cannot hide in a nested object I did not think to print."""
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            out += walk(v, prefix + "." + k if prefix else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out += walk(v, "%s[%d]" % (prefix, i))
    else:
        out.append((prefix, o))
    return out


saved = {}
for eid in ("52060", "52061", "52059"):
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        j = run["Webhook"][0]["data"]["main"][0][0].get("json") or {}
    except Exception as e:
        print("exec %s: no webhook data (%s)" % (eid, e))
        continue
    body = j.get("body") or {}
    saved[eid] = body
    print("=" * 78)
    print("exec %s  event=%r" % (eid, body.get("event_type")))
    print("=" * 78)
    print("--- COMPLETE raw body, every leaf ---")
    for path, val in walk(body):
        s = repr(val)
        if len(s) > 160:
            s = s[:160] + "…"
        print("   %-58s = %s" % (path, s))

    print("\n--- Normalize's msgs, as WF-1 sees them ---")
    try:
        nz = run["Normalize"][0]["data"]["main"][0][0]["json"]
        print("   Normalize keys: %s" % sorted(nz.keys()))
        msgs = nz.get("msgs")
        print("   msgs type=%s len=%s" % (type(msgs).__name__,
                                          len(msgs) if isinstance(msgs, list) else "n/a"))
        if isinstance(msgs, list):
            for i, m in enumerate(msgs):
                print("     [%d] %s" % (i, json.dumps(m, ensure_ascii=False)[:400]))
    except Exception as e:
        print("   (Normalize not captured: %s)" % e)

    print("\n--- what M7 Build produced, if it ran ---")
    for nm in ("M7 Build",):
        if nm not in run:
            print("   %s did not run" % nm)
            continue
        try:
            it = run[nm][0]["data"]["main"][0][0]["json"]
            for k in ("reply_text", "reply_note", "alert_text"):
                if k in it:
                    print("   %-12s = %r" % (k, str(it[k])[:200]))
        except Exception as e:
            print("   (%s)" % e)

print("\n" + "=" * 78)
print("KEYS ACROSS ALL THREE BODIES (union) - is there ANY attachment-ish field?")
print("=" * 78)
allkeys = set()
for body in saved.values():
    allkeys |= {p for p, _ in walk(body)}
for k in sorted(allkeys):
    print("   %s" % k)
hits = [k for k in allkeys
        if any(t in k.lower() for t in ("attach", "media", "file", "image", "doc", "type",
                                        "kind", "content"))]
print("\n   attachment-ish paths: %s" % (hits or "NONE"))

with open(os.path.join(HERE, "heath_raw_bodies.json"), "w", encoding="utf-8") as f:
    json.dump(saved, f, ensure_ascii=False, indent=1)
print("\n-> heath_raw_bodies.json")
