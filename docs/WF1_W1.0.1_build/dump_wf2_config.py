#!/usr/bin/env python3
"""Dump WF-2's CONFIG values the Andrea repair must reuse verbatim, plus the two body builders'
exact field lines. The repair writes what WF-2 would have written - so the constants come from
WF-2, not from me."""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

with urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/v1/workflows/jp7rum9Z0YDJkQWv",
        headers={"X-N8N-API-KEY": KEY}), timeout=150, context=ctx) as x:
    wf = json.load(x)
N = {n["name"]: n for n in wf["nodes"]}

blob = json.dumps(N["CONFIG"]["parameters"])
m = re.search(r'\{[^"]*"pipedrive_base".*?\}\s*"', blob)
cfg = None
for cand in re.findall(r'"(\{.*?\})"', blob, re.S):
    try:
        cfg = json.loads(cand.encode().decode("unicode_escape"))
        break
    except Exception:
        continue
if cfg is None:
    raw = blob.encode().decode("unicode_escape")
    i = raw.find("{", raw.find("pipedrive_base") - 400)
    print("could not parse CONFIG as JSON; raw slice:")
    print(raw[max(0, i):i + 2500])
else:
    for k in ("owner_id", "lead_channel", "lead_opportunity_type_value", "labels",
              "team_channel", "ops_channel", "pipedrive_base", "sl_inbox_base",
              "activity_type", "reply_activity_type", "alert_every_reply"):
        print(f"  {k:<28} {json.dumps(cfg.get(k))[:150]}")
    F = cfg.get("fields") or {}
    print(f"\n  fields ({len(F)} keys):")
    for k, v in F.items():
        print(f"     {k:<32} {v}")

print("\n=== Body Lead Create : title line + body ===")
js = N["Body Lead Create"]["parameters"]["jsCode"]
for i, l in enumerate(js.splitlines(), 1):
    if 13 <= i <= 27:
        print(f"{i:>3}| {l.rstrip()}")

print("\n=== Body Reply Activity : the body object ===")
js2 = N["Body Reply Activity"]["parameters"]["jsCode"]
lines = js2.splitlines()
start = next((i for i, l in enumerate(lines) if "const body" in l), 0)
for i in range(start, min(start + 26, len(lines))):
    print(f"{i+1:>3}| {lines[i].rstrip()}")

print("\n=== Body Lead Labels Union : which label id it adds on a reply ===")
js3 = N["Body Lead Labels Union"]["parameters"]["jsCode"]
for i, l in enumerate(js3.splitlines(), 1):
    if re.search(r"labels\.|responded|union|label_ids", l):
        print(f"{i:>3}| {l.rstrip()[:112]}")
