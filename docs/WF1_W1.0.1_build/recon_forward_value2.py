#!/usr/bin/env python3
"""Forward-value recon, SUMMARISED. The estate declares 710 sending mailboxes; listing them all
buries the answer. What matters is the ratio: how many are the owner's own inbox (forward =
duplicate) versus a sending-domain box (forward = the only bridge to a human).
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter, defaultdict

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
            timeout=150, context=ctx) as x:
        return json.load(x)


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
cfgn = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
raw = next(v for v in (cfgn.get("parameters") or {}).values()
           if isinstance(v, str) and "forward_inbox_map" in v)
cfg = json.loads(raw)
inbox_map = cfg.get("forward_inbox_map") or {}
owner_map = cfg.get("forward_owner_map") or {}

print(f"sending mailboxes declared : {len(inbox_map)}")
print(f"owners                     : {len(owner_map)}  {sorted(owner_map)}")
print(f"owners' REAL inboxes       :")
for k, v in sorted(owner_map.items()):
    print(f"   {k:<12} {v}")

dup, bridge, unmapped = [], [], []
send_domains = Counter()
for sender, owner in inbox_map.items():
    real = owner_map.get(owner)
    send_domains[sender.split("@")[-1].lower()] += 1
    if not real:
        unmapped.append(sender)
    elif str(real).lower() == sender.lower():
        dup.append(sender)
    else:
        bridge.append((sender, real))

print(f"\nCLASSIFICATION OF THE {len(inbox_map)} SENDING MAILBOXES")
print(f"   identical to the owner's real inbox (forward = DUPLICATE) : {len(dup)}")
for s in dup[:12]:
    print(f"      {s}")
print(f"   different address (forward = BRIDGE)                      : {len(bridge)}")
print(f"   owner has no mapped real inbox                            : {len(unmapped)}")

print(f"\nSENDING DOMAINS ({len(send_domains)} distinct)")
for d, n in send_domains.most_common(20):
    real_doms = {str(v).split('@')[-1].lower() for v in owner_map.values()}
    tag = "  <-- also a REAL owner domain" if d in real_doms else ""
    print(f"   {d:<34} {n}{tag}")

print("\nWHAT ACTUALLY SENDS IN LIVE CAMPAIGNS")
camps = sl("/campaigns") or []
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
live = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING")]
print(f"   active campaigns: {len(live)}")
seen = Counter()
for c in live:
    accts = sl(f"/campaigns/{c.get('id')}/email-accounts")
    accts = accts if isinstance(accts, list) else (accts.get("data") or [])
    mails = sorted({str(a.get("from_email") or a.get("email") or "").lower()
                    for a in accts if isinstance(a, dict)} - {""})
    for m in mails:
        seen[m.split("@")[-1]] += 1
    print(f"   {c.get('id')} {str(c.get('name'))[:38]:<40} senders={len(mails)} "
          f"domains={sorted({m.split('@')[-1] for m in mails})}")

print("\nVERDICT")
real_doms = {str(v).split('@')[-1].lower() for v in owner_map.values()}
live_on_real = sum(n for d, n in seen.items() if d in real_doms)
live_on_send = sum(n for d, n in seen.items() if d not in real_doms)
print(f"   live campaign sender accounts on an OWNER'S REAL domain : {live_on_real}")
print(f"   live campaign sender accounts on a SENDING domain       : {live_on_send}")
print("\n   NOT ANSWERABLE FROM ANY API — needs Melisa/Nik: whether a human READS the")
print("   sending-domain mailboxes. If yes, those forwards duplicate too; if no, the forward")
print("   is the ONLY path from a campaign reply to a person.")
