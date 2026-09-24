#!/usr/bin/env python3
"""Two gaps in my own population check:
  (a) are the 9 'nothing' members people we FAILED to create, or simply not sent to yet? The
      campaign is ACTIVE - a member with no SENT has no lead because none is due, not because
      anything broke. That distinction decides whether a backfill is a repair or a policy change.
  (b) the HeyReach Finovate campaign exists and I counted it without enumerating its members.
"""
import json, os, ssl, urllib.parse, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
HR = os.environ.get("HEYREACH_API_KEY")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


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
                               headers={"X-API-KEY": HR, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


pop = json.load(open(os.path.join(HERE, "finovate_population.json"), encoding="utf-8"))
gap = [r for r in pop["members"] if r["state"] in ("person_only", "nothing")]
print(f"(a) the {len(gap)} members with no lead — have they actually been SENT to?\n")

sent_map = {}
for cid in (3868449, 3868450):
    off = 0
    while off < 3000:
        r = sl(f"/campaigns/{cid}/leads-statistics", limit=100, offset=off)
        rows = (r or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            to = str(row.get("to") or "").lower()
            hist = row.get("history") or []
            sent_map[to] = [str(h.get("type")) for h in hist]
        if not r.get("hasMore"):
            break
        off += 100

never_sent, sent_no_lead = [], []
for g in gap:
    h = sent_map.get(g["email"])
    if not h or "SENT" not in h:
        never_sent.append(g)
    else:
        sent_no_lead.append({**g, "history": h})
print(f"  never sent to (no lead is CORRECT, nothing broke) : {len(never_sent)}")
print(f"  SENT but still no lead (a real gap)              : {len(sent_no_lead)}")
for g in sent_no_lead[:8]:
    print(f"     {g['email']:<40} {g['segment']:<10} history={g['history']}")
for g in never_sent[:5]:
    print(f"     (pending) {g['email']:<34} {g['segment']}")

print(f"\n(b) HeyReach Finovate campaign members\n")
hc = hr("/campaign/GetAll", {"offset": 0, "limit": 100})
fin = [c for c in (hc.get("items") or [])
       if "finovate" in str(c.get("name") or "").lower()]
hr_rows = []
for c in fin:
    cid = c.get("id")
    print(f"  campaign {cid}: {c.get('name')!r} status={c.get('status')}")
    off = 0
    while off < 3000:
        r = hr("/campaign/GetLeadsFromCampaign",
               {"campaignId": cid, "offset": off, "limit": 100})
        items = (r or {}).get("items") or []
        if not items:
            break
        for it in items:
            p = it.get("lead") or it.get("profile") or it
            hr_rows.append({"campaign_id": cid,
                            "name": " ".join(filter(None, [p.get("firstName"),
                                                           p.get("lastName")])) or None,
                            "profile": p.get("profileUrl") or p.get("linkedin_id"),
                            "email": (p.get("emailAddress") or p.get("email") or None)})
        off += 100
        if len(items) < 100:
            break
    print(f"     members pulled: {len([x for x in hr_rows if x['campaign_id'] == cid])}")

with_email = [x for x in hr_rows if x["email"]]
print(f"  HeyReach members total: {len(hr_rows)}   with an email: {len(with_email)}")
if hr_rows:
    print(f"  sample: {json.dumps(hr_rows[:3], ensure_ascii=False)[:220]}")

json.dump({"never_sent": never_sent, "sent_no_lead": sent_no_lead, "heyreach": hr_rows},
          open(os.path.join(HERE, "finovate_gap_detail.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: finovate_gap_detail.json")
