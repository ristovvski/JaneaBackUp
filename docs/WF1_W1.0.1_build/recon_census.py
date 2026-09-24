#!/usr/bin/env python3
"""Naming census, both providers + the full WF-2 campaign_event_map. READ ONLY."""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SL = os.environ["SMARTLEAD_API_KEY"]
HR = os.environ.get("HEYREACH_API_KEY")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


def hr(p, b):
    r = urllib.request.Request("https://api.heyreach.io/api/public" + p, method="POST",
                               data=json.dumps(b).encode(),
                               headers={"X-API-KEY": HR, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


print("=" * 78)
print("WF-2 CONFIG.campaign_event_map — the ID allowlist for EMAIL event capture")
print("=" * 78)
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
cfg = json.loads(next(n for n in wf2["nodes"] if n["name"] == "CONFIG")
                 ["parameters"]["jsonOutput"])
cem = cfg.get("campaign_event_map") or {}
print(f"entries: {len(cem)}")
for cid, v in cem.items():
    nm = sl(f"/campaigns/{cid}")
    print(f"   {cid}  hypothesis={v.get('hypothesis')!r} event_name={v.get('event_name')!r}")
    print(f"        actual name: {str((nm or {}).get('name'))!r}")

print("\n" + "=" * 78)
print("HeyReach — every campaign name")
print("=" * 78)
off, all_hr = 0, []
while off < 500:
    c = hr("/campaign/GetAll", {"offset": off, "limit": 100})
    items = (c or {}).get("items") or []
    if not items:
        break
    all_hr += items
    off += 100
    if off >= (c.get("totalCount") or 0):
        break
print(f"campaigns: {len(all_hr)}")
BR = re.compile(r"\[([^\]]*)\]")
for c in sorted(all_hr, key=lambda x: str(x.get("name"))):
    nm = str(c.get("name") or "")
    g = BR.findall(nm)
    ok = len(g) >= 2 and g[0].strip().lower() == "events visiting"
    flag = "  <-- PARSES" if ok else ("  <-- brackets but NOT canon" if g else "")
    print(f"   {c.get('id'):<10} {nm[:62]:<62}{flag}")

print("\n" + "=" * 78)
print("Smartlead — every campaign name")
print("=" * 78)
camps = sl("/campaigns")
camps = camps if isinstance(camps, list) else []
print(f"campaigns: {len(camps)}")
pat = {}
for c in sorted(camps, key=lambda x: str(x.get("name"))):
    nm = str(c.get("name") or "")
    g = BR.findall(nm)
    tag = g[0].strip() if g else "(no bracket)"
    pat.setdefault(tag, []).append((c.get("id"), nm, c.get("status")))
for tag, rows in sorted(pat.items(), key=lambda t: -len(t[1])):
    print(f"\n   [{tag}]  x{len(rows)}")
    for cid, nm, st in rows[:8]:
        inmap = "  IN campaign_event_map" if str(cid) in cem else ""
        print(f"      {cid:<10} {nm[:60]:<60} {st}{inmap}")
    if len(rows) > 8:
        print(f"      ... {len(rows)-8} more")
