#!/usr/bin/env python3
"""Fetch REAL campaign names for all 6 S4 campaigns (4 Smartlead + 2 HeyReach), parse sender per
the "[Events Visiting] [Event] - Sender - Channel" grammar, and build a lead_id -> campaign_id
map by re-fetching each campaign's lead list (small: ~892 Smartlead + ~1270 HeyReach total per
the S4 build's own comment -- cheap, safe reads). Read-only, no writes."""
import json, os, re, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
SL_TOKEN = os.environ["SMARTLEAD_API_KEY"]
HR_TOKEN = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else ssl.create_default_context()

S4_SMARTLEAD_CAMPAIGNS = [3686193, 3686187, 3686184, 3686181]
S4_HEYREACH_CAMPAIGNS = [513000, 512995]


def sl_get(path, params=None):
    params = dict(params or {})
    params["api_key"] = SL_TOKEN
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}?{qs}",
                                  headers={"accept": "application/json", "User-Agent": "Mozilla/5.0 janea-owner-tag/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


def hr_post(path, body):
    req = urllib.request.Request(f"https://api.heyreach.io/api/public{path}", method="POST",
                                  data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json", "X-API-KEY": HR_TOKEN,
                                           "User-Agent": "Mozilla/5.0 janea-owner-tag/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


def parse_sender(campaign_name):
    # two-bracket contract first: "[Events Visiting] [Event Token] - Sender - Channel"
    m = re.match(r"^\[[^\]]*\]\s*\[[^\]]*\]\s*-\s*([^-]+?)\s*-\s*(.+)$", campaign_name)
    if m:
        return m.group(1).strip(), m.group(2).strip(), "two-bracket"
    # fallback: older single-bracket form still carries the same trailing "- Sender - Channel"
    m = re.match(r"^\[[^\]]*\]\s*[^-]*-\s*([^-]+?)\s*-\s*(.+)$", campaign_name)
    if m:
        return m.group(1).strip(), m.group(2).strip(), "single-bracket-fallback"
    return None, None, "unparsed"


lead_to_campaign = {}
campaign_info = {}

print("=== Smartlead campaigns ===")
for cid in S4_SMARTLEAD_CAMPAIGNS:
    info = sl_get(f"/campaigns/{cid}")
    name = info.get("name")
    sender, channel, mode = parse_sender(name or "")
    campaign_info[f"smartlead:{cid}"] = {"name": name, "sender": sender, "channel": channel, "parse_mode": mode}
    print(f"  {cid}: {name!r} -> sender={sender!r} channel={channel!r} ({mode})")
    offset = 0
    while True:
        page = sl_get(f"/campaigns/{cid}/leads", {"offset": offset, "limit": 100})
        rows = page.get("data") or []
        if not rows:
            break
        for row in rows:
            lead = row.get("lead") or {}
            lid = lead.get("id") or row.get("campaign_lead_map_id")
            if lid is not None:
                lead_to_campaign[f"smartlead:{lid}"] = cid
        total = int(page.get("total_leads") or len(rows))
        offset += len(rows)
        if offset >= total or len(rows) < 100:
            break
        time.sleep(0.2)
    print(f"    {offset} leads mapped")

print("\n=== HeyReach campaigns ===")
for cid in S4_HEYREACH_CAMPAIGNS:
    # HeyReach campaign name -- try a list-and-filter since no direct GET /campaign/{id} confirmed
    campaigns = hr_post("/campaign/GetAll", {})
    items = campaigns.get("items") if isinstance(campaigns, dict) else campaigns
    match = next((c for c in (items or []) if c.get("id") == cid), None)
    name = (match or {}).get("name")
    sender, channel, mode = parse_sender(name or "")
    campaign_info[f"heyreach:{cid}"] = {"name": name, "sender": sender, "channel": channel, "parse_mode": mode}
    print(f"  {cid}: {name!r} -> sender={sender!r} channel={channel!r} ({mode})")
    offset = 0
    while True:
        page = hr_post("/campaign/GetLeadsFromCampaign", {"campaignId": cid, "limit": 100, "offset": offset})
        items2 = page.get("items") or []
        if not items2:
            break
        for it in items2:
            lid = it.get("id")
            if lid is not None:
                lead_to_campaign[f"heyreach:{lid}"] = cid
        total = int(page.get("totalCount") or len(items2))
        offset += len(items2)
        if offset >= total or len(items2) < 100:
            break
        time.sleep(0.2)
    print(f"    {offset} leads mapped")

with open(os.path.join(HERE, "fixtures", "s4_campaign_senders.json"), "w", encoding="utf-8") as f:
    json.dump({"campaign_info": campaign_info, "lead_to_campaign": lead_to_campaign}, f, indent=1)
print(f"\nwrote fixtures/s4_campaign_senders.json ({len(lead_to_campaign)} lead->campaign mappings)")
