#!/usr/bin/env python3
"""Redo the reachability check with the REAL key. The first attempt could not match and said "0".

`__sent_seen_v2` is keyed by a UUID (`b.__key`), not by campaign+lead, so matching on campaign+lead
was guaranteed to find nothing and report every event reachable. All 32 crashed SENTs carry
`__reconciled_by`, i.e. they arrived through WF-2S's own replay - which means `Summary` marked them
seen. If so they are NOT self-recovering, and my earlier "32 recoverable" was wrong.

Find the actual key on both sides and compare like with like.
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
SINCE = datetime.fromisoformat("2026-08-11T14:30:00+00:00")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


ws = n8n(f"/api/v1/workflows/{WF2S}")
print("A. how WF-2S builds its key")
for nm in ("Find New Sends", "Build SENT Payload"):
    n = next((x for x in ws["nodes"] if x["name"] == nm), None)
    js = ((n or {}).get("parameters") or {}).get("jsCode") or ""
    for i, line in enumerate(js.splitlines(), 1):
        if "__key" in line or "key =" in line or "key:" in line:
            print(f"   {nm}:{i}| {line.strip()[:118]}")

sd = (ws.get("staticData") or {}).get("global") or {}
sent_seen = sd.get("__sent_seen_v2") or {}
print(f"\n   __sent_seen_v2: {len(sent_seen)} entries, key sample {list(sent_seen)[:2]}")

print("\nB. crashed SENTs - pull whatever identifier the replay carried")
p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": "error"})
crashed = []
for e in ((p or {}).get("data") or []):
    if (ts(e.get("startedAt")) or SINCE) < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    if nm.get("event") != "SENT":
        continue
    wh = {}
    try:
        wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
    cand = {k: v for k, v in (body or {}).items()
            if isinstance(v, str) and len(v) in (36, 32) and "-" in v}
    crashed.append({"exec": e["id"], "email": (nm.get("lead") or {}).get("email"),
                    "uuidish": cand, "stats_id": (nm.get("reply") or {}).get("stats_id"),
                    "map": nm.get("sl_lead_map_id"), "by": nm.get("__reconciled_by")})

print(f"   crashed SENT: {len(crashed)}")
if crashed:
    print(f"   sample uuid-ish fields on the replayed payload: "
          f"{json.dumps(crashed[0]['uuidish'], ensure_ascii=False)[:260]}")

hits = 0
for c in crashed:
    vals = set(str(v) for v in (c["uuidish"] or {}).values())
    vals |= {str(c["stats_id"]), str(c["map"])}
    if vals & set(sent_seen.keys()):
        hits += 1
print(f"\n   crashed events whose key IS in __sent_seen_v2 (WF-2S will NOT retry): {hits}")
print(f"   crashed events WF-2S would still pick up                            : {len(crashed) - hits}")
print(f"   arrived via WF-2S replay (__reconciled_by): "
      f"{sum(1 for c in crashed if c.get('by'))}/{len(crashed)}")

print("\nC. verdict")
if hits or all(c.get("by") for c in crashed):
    print("   *** NOT self-recovering. WF-2S replayed these, marked them seen in __sent_seen_v2,")
    print("       and WF-2 then crashed on the 429. Unclaimed in wf2_seen means they are not LOST -")
    print("       nothing will double-process them - but nothing will retry them either.")
    print("       Fix: release their WF-2S keys so the reconciler re-detects them.")
else:
    print("   reachable - the earlier claim holds.")
