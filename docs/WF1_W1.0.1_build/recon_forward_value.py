#!/usr/bin/env python3
"""Item 7 - when does the FORWARD actually add value? Read-only recon, no changes.

The question: replies land in whatever mailbox Smartlead sends from. If that mailbox IS the owner's
real inbox, our forward duplicates mail they already have. If it is a SENDING-DOMAIN box
(janeatechinnovate.com / janeasoftwaredevs.co), the forward is the bridge to the human.

Mechanically answerable from two sources:
  * WF-2 CONFIG `forward_inbox_map` (sending mailbox -> owner NAME) and `forward_owner_map`
    (owner name -> owner's REAL inbox) - the estate's own declaration of who owns what
  * Smartlead's per-campaign email accounts - what actually sends

NOT answerable from any API, and flagged as such: whether a human actually READS the sending-domain
mailbox. That is a process fact for Melisa/Nik, and the recon must not pretend otherwise.
"""
import json, os, re, ssl, urllib.parse, urllib.request
from collections import Counter, defaultdict

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


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


print("A. THE ESTATE'S OWN DECLARATION (WF-2 CONFIG forward maps)")
wf = n8n(f"/api/v1/workflows/{WF2}")
cfgn = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
raw = None
for v in (cfgn.get("parameters") or {}).values():
    if isinstance(v, str) and "forward_inbox_map" in v:
        raw = v
        break
cfg = json.loads(raw) if raw else {}
inbox_map = cfg.get("forward_inbox_map") or {}
owner_map = cfg.get("forward_owner_map") or {}
print(f"   forward_inbox_map  ({len(inbox_map)} sending mailboxes -> owner name)")
for k, v in inbox_map.items():
    print(f"      {k:<44} -> {v}")
print(f"   forward_owner_map  ({len(owner_map)} owner -> REAL inbox)")
for k, v in owner_map.items():
    print(f"      {k:<20} -> {v}")
print(f"   forward_default    : {cfg.get('forward_default')}")
print(f"   forward_review_addr: {cfg.get('forward_review_address')}")

print("\nB. DOES THE SENDING MAILBOX EQUAL THE OWNER'S REAL INBOX?")
rows = []
for sender, owner in inbox_map.items():
    real = owner_map.get(owner)
    s_dom = sender.split("@")[-1].lower()
    r_dom = str(real or "").split("@")[-1].lower()
    same_addr = (str(real or "").lower() == sender.lower())
    same_dom = bool(r_dom) and s_dom == r_dom
    verdict = ("DUPLICATE - forward adds nothing" if same_addr
               else ("same domain, different box" if same_dom
                     else "BRIDGE - sending domain differs from the owner's inbox"))
    rows.append((sender, owner, real, verdict))
    print(f"   {sender:<44} owner={str(owner):<8} real={str(real):<32} {verdict}")

print("\nC. WHAT ACTUALLY SENDS, PER CAMPAIGN (Smartlead)")
camps = sl("/campaigns") or []
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
active = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING",
                                                                  "COMPLETED", "PAUSED")]
print(f"   campaigns: {len(camps)} total; inspecting the {min(len(active), 12)} most recent")
dom_counter = Counter()
per_campaign = {}
for c in sorted(active, key=lambda x: str(x.get("created_at")), reverse=True)[:12]:
    cid = c.get("id")
    accts = sl(f"/campaigns/{cid}/email-accounts")
    accts = accts if isinstance(accts, list) else (accts.get("data") or [])
    mails = sorted({str(a.get("from_email") or a.get("email") or "").lower()
                    for a in accts if isinstance(a, dict)} - {""})
    per_campaign[cid] = (c.get("name"), c.get("status"), mails)
    for m in mails:
        dom_counter[m.split("@")[-1]] += 1
    print(f"   [{str(c.get('status'))[:9]:<9}] {cid} {str(c.get('name'))[:40]:<42} "
          f"senders={mails if mails else 'none returned'}")

print("\nD. SENDING DOMAINS IN USE")
for d, n in dom_counter.most_common():
    print(f"   {d:<34} {n} campaign-account(s)")

print("\nE. VERDICT")
bridges = [r for r in rows if r[3].startswith("BRIDGE")]
dupes = [r for r in rows if r[3].startswith("DUPLICATE")]
print(f"   sending mailboxes that are the owner's OWN inbox (forward = duplicate): {len(dupes)}")
print(f"   sending mailboxes on a DIFFERENT domain (forward = the bridge)        : {len(bridges)}")
if bridges:
    print("   => the forward mechanism is NOT redundant estate-wide. It is load-bearing for:")
    for s, o, r, _ in bridges:
        print(f"        {s}  ->  {r}")
print("\n   NOT ANSWERABLE FROM ANY API - needs Melisa/Nik:")
print("   whether a human actually READS the sending-domain mailboxes above. If someone does,")
print("   those forwards are duplicates too; if nobody does, they are the only delivery path.")
