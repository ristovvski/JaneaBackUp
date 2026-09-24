#!/usr/bin/env python3
"""Do reply webhooks stop when a campaign is PAUSED - and if so, does WF-2R actually cover it?

Melisa: notifications stopped when Stefan paused two campaigns. Two independent failure modes, and
they compound:
  A. Smartlead/HeyReach stop DELIVERING EMAIL_REPLY webhooks for a paused campaign (detection gap).
  B. WF-2R's own campaign picker filters to active campaigns, so the safety net has the SAME blind
     spot as the thing it is meant to back up. That would make the pause a total blackout.

B is decidable offline from the deployed nodes - do that first, it costs nothing and it is the part
we control. Then get the facts for A: which campaigns are paused, since when, and whether replies
exist with reply_time AFTER the pause.

Read-only. No writes anywhere.
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SLB = "https://server.smartlead.ai/api/v1"


def n8n(p):
    with urllib.request.urlopen(urllib.request.Request(
            BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=150, context=ctx) as x:
        return json.load(x)


def sl(p, **q):
    q["api_key"] = SL
    url = f"{SLB}{p}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


print("=" * 78)
print("PART B - does WF-2R's own picker skip paused campaigns? (we control this)")
print("=" * 78)
wf = n8n("/api/v1/workflows/U8Bb7Pdq7S6nzYPa")
NODES = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2R versionId={wf.get('versionId')} active={wf.get('active')}\n")

for nm in ("CONFIG", "SL Campaigns", "Pick Campaign", "SL Leads Statistics", "Find New Replies"):
    n = NODES.get(nm)
    if not n:
        print(f"--- {nm}: ABSENT ---")
        continue
    js = (n.get("parameters") or {}).get("jsCode") or ""
    print(f"--- {nm} ({n['type'].split('.')[-1]}) ---")
    if js:
        for i, line in enumerate(js.splitlines(), 1):
            if re.search(r"status|STATUS|paused|PAUSED|active|ACTIVE|lookback|hours|days|since|"
                         r"window|_ms|DRAFTED|COMPLETED|STOPPED", line):
                print(f"  {i:>3}| {line.rstrip()[:112]}")
    else:
        p = json.dumps(n.get("parameters") or {})
        for m in re.findall(r'.{0,60}(?:status|url|lookback|limit|offset).{0,70}', p, re.I)[:8]:
            print(f"      {m}")
    print()

print("=" * 78)
print("PART A - which campaigns are paused, and do replies land after the pause?")
print("=" * 78)
camps = sl("/campaigns")
if isinstance(camps, dict) and camps.get("__err"):
    print("campaign list failed:", camps["__err"])
    camps = []
by_status = {}
for c in camps if isinstance(camps, list) else []:
    by_status.setdefault(str(c.get("status")), []).append(c)
print("campaigns by status:")
for s, v in sorted(by_status.items(), key=lambda t: -len(t[1])):
    print(f"   {s:<12} {len(v)}")

paused = by_status.get("PAUSED", []) + by_status.get("STOPPED", [])
print(f"\npaused/stopped campaigns: {len(paused)}")
for c in paused:
    print(f"   {c.get('id')}  {str(c.get('name'))[:52]!r}  "
          f"status={c.get('status')}  updated={c.get('updated_at')}")

# do those campaigns have replies, and how recent? leads-statistics caps limit at 100.
print("\nreplies recorded by Smartlead for paused campaigns (provider truth, not our webhooks):")
for c in paused[:6]:
    cid = c.get("id")
    st = sl(f"/campaigns/{cid}/leads-statistics", limit=100, offset=0)
    rows = (st or {}).get("data") or [] if isinstance(st, dict) else []
    reps = [r for r in rows if r.get("reply_time")]
    reps.sort(key=lambda r: str(r.get("reply_time")), reverse=True)
    print(f"   campaign {cid} ({str(c.get('name'))[:34]!r}): rows={len(rows)} "
          f"with reply_time={len(reps)}  updated_at={c.get('updated_at')}")
    for r in reps[:4]:
        after = str(r.get("reply_time") or "") > str(c.get("updated_at") or "")
        print(f"      reply {r.get('reply_time')}  {str(r.get('lead_email'))[:38]}"
              f"{'   <-- AFTER the status change' if after else ''}")
