#!/usr/bin/env python3
"""Map every Slack node in WF-1 / WF-2 / WF-2R / WF-2S / WF-2H to the CONFIG key it resolves, and
classify it reply vs non-reply.

The routing spec is CONFIG-level, not per-node hardcode - so before switching anything, this
answers the only question that matters: does exactly one key feed the reply alerts, and does
nothing else share that key? If an ops warning also reads slack_channel_replies, flipping that key
would push a watchdog alarm into the team channel, which the spec forbids.

Run with --verify after the switch: exits non-zero if ANY non-reply Slack node resolves to the
team channel.
"""
import argparse, json, os, re, ssl, sys, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
TEAM = "C07LTD8UT70"
OPS = "C0B8GCVNR5W"
WORKFLOWS = {"WF-1": "2jdjKM2NJr473GdA", "WF-2": "jp7rum9Z0YDJkQWv",
             "WF-2R": "U8Bb7Pdq7S6nzYPa", "WF-2S": "6Y92ryBwYoy6z0Jx",
             "WF-2H": "nK3yIOqRcBearV8s"}
# a node is a REPLY notification only if it announces an inbound reply to humans
REPLY_NODES = {"M7 Critical Slack", "Reply Alert", "Nurture Alert"}


def n8n(path):
    r = urllib.request.Request(BASE + path,
                               headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


ap = argparse.ArgumentParser()
ap.add_argument("--verify", action="store_true")
a = ap.parse_args()

problems, rows = [], []
for label, wid in WORKFLOWS.items():
    wf = n8n(f"/api/v1/workflows/{wid}")
    cfg_node = next((n for n in wf["nodes"] if n["name"] == "CONFIG"), None)
    cfg = json.loads(cfg_node["parameters"]["jsonOutput"]) if cfg_node else {}
    for n in wf["nodes"]:
        if n.get("type") != "n8n-nodes-base.slack":
            continue
        raw = json.dumps((n.get("parameters") or {}).get("channelId") or {}, ensure_ascii=False)
        m = re.search(r"json\.(\w+)", raw)
        key = m.group(1) if m else None
        resolved = cfg.get(key) if key else None
        if resolved is None:
            m2 = re.search(r"(C0[A-Z0-9]{8,})", raw)
            resolved = m2.group(1) if m2 else "(unresolved)"
            key = key or "(hardcoded)"
        is_reply = n["name"] in REPLY_NODES
        rows.append({"wf": label, "node": n["name"], "config_key": key,
                     "resolves_to": resolved, "reply": is_reply})
        if resolved == TEAM and not is_reply:
            problems.append(f"{label}/{n['name']} is NOT a reply node but resolves to the team "
                            f"channel via {key}")

print(f"{'workflow':<7} {'node':<28} {'CONFIG key':<32} {'->':<3} {'channel':<13} kind")
print("-" * 104)
for r in sorted(rows, key=lambda x: (x["wf"], x["node"])):
    ch = r["resolves_to"]
    tag = "TEAM" if ch == TEAM else ("ops" if ch == OPS else "?")
    print(f"{r['wf']:<7} {r['node']:<28} {str(r['config_key']):<32} ->  {str(ch):<13} "
          f"{'REPLY' if r['reply'] else 'other':<6} [{tag}]")

keys_used_by_reply = sorted({r["config_key"] for r in rows if r["reply"]})
keys_used_by_other = sorted({r["config_key"] for r in rows if not r["reply"]})
shared = sorted(set(keys_used_by_reply) & set(keys_used_by_other))
print(f"\nCONFIG keys feeding REPLY nodes : {keys_used_by_reply}")
print(f"CONFIG keys feeding other nodes : {keys_used_by_other}")
print(f"SHARED keys (must be empty to switch safely): {shared}")

print(f"\nnon-reply nodes resolving to the team channel: {len(problems)}")
for p in problems:
    print("  -", p)

if a.verify:
    ok = not problems and not shared
    print(f"\nVERIFY: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
