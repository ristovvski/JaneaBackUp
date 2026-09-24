#!/usr/bin/env python3
"""READ ONLY. Question 2 needs the actual Slack post, not the fact that a gate opened.

`Critical Slack` is WF-1's node name; WF-2's alert node is called something else, so the first pass
printed the gate but never the delivery. Enumerate every Slack node in WF-2, then report which of
the five amity.curry executions actually produced a message, in which channel, with which ts.
"""
import json
import os
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
EXECS = ["48527", "48544", "48554", "48557", "48602"]


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:140]}


wf = n8n("/api/v1/workflows/%s" % WF2)
slack_nodes = [n["name"] for n in wf["nodes"] if n["type"].endswith("slack")]
print("Slack nodes in WF-2 (%d): %s\n" % (len(slack_nodes), slack_nodes))
chan = {}
for n in wf["nodes"]:
    if n["type"].endswith("slack"):
        chan[n["name"]] = json.dumps((n.get("parameters") or {}).get("channelId"),
                                     ensure_ascii=False)

cfg = next((n for n in wf["nodes"] if n["name"] == "CONFIG"), None)
vals = {a["name"]: a["value"] for a in
        ((cfg["parameters"].get("assignments") or {}).get("assignments") or [])} if cfg else {}
print("CONFIG channels: %s\n" % json.dumps(
    {k: v for k, v in vals.items() if "channel" in k.lower()}, ensure_ascii=False))

for eid in EXECS:
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    rd = (((f or {}).get("data") or {}).get("resultData") or {})
    run = rd.get("runData") or {}
    fired = []
    for nm in slack_nodes:
        if nm not in run:
            continue
        try:
            its = [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
        except Exception:
            its = []
        fired.append((nm, its))
    print("exec %s  nodes_run=%d  slack nodes that RAN: %s" % (
        eid, len(run), [f[0] for f in fired] or "none"))
    for nm, its in fired:
        print("    %-26s param_channel=%s" % (nm[:26], chan.get(nm, "?")[:80]))
        for it in its[:2]:
            keep = {k: it.get(k) for k in ("ok", "channel", "ts", "message_timestamp", "error")
                    if k in it}
            msg = it.get("message") or {}
            if isinstance(msg, dict):
                keep["msg_text"] = str(msg.get("text") or "")[:220]
                keep["msg_ts"] = msg.get("ts")
            print("        %s" % json.dumps(keep, ensure_ascii=False)[:600])
