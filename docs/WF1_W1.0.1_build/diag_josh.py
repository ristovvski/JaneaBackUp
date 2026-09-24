#!/usr/bin/env python3
"""Person-7cb57cf4 trace + the 14-day manual-conversation alert count. READ ONLY."""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
TEAM = "C07LTD8UT70"


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


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


print("=" * 78)
print("JOSH — does he exist in Pipedrive under ANY identity form?")
print("=" * 78)
for label, term in (("name", "Person-7cb57cf4"), ("slug", "josh803316"),
                    ("url", "linkedin.com/in/pii-371e2e0b")):
    r = pd(f"/api/v2/persons/search?limit=5&term={urllib.parse.quote(term)}")
    items = ((r or {}).get("data") or {}).get("items") or []
    print(f"  by {label:<5} {term!r:<32} -> {len(items)} hit(s) "
          f"{[( (i.get('item') or {}).get('id'), (i.get('item') or {}).get('name')) for i in items[:3]]}")

print("\n" + "=" * 78)
print("WF-1 executions mentioning Nisenson / josh803316")
print("=" * 78)
cur, pages, found = None, 0, []
alerts = []
CUT = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
while pages < 8:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if not rd:
            continue
        blob = json.dumps(rd)

        def o(nm):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"]
            except Exception:
                return None

        if "Nisenson" in blob or "josh803316" in blob:
            found.append((r, rd))
        # 14-day alert census
        cs = o("M7 Critical Slack") or {}
        if cs.get("ok") is True and cs.get("channel") == TEAM and str(r.get("startedAt")) >= CUT:
            nz = o("Normalize") or {}
            camp = nz.get("campaign") or {}
            alerts.append({"at": r.get("startedAt"), "lead": (nz.get("lead") or {}).get("full_name"),
                           "campaign": camp.get("name"), "campaign_id": camp.get("id"),
                           "event": nz.get("event")})
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break

print(f"  pages walked: {pages}   Josh executions: {len(found)}")
for r, rd in sorted(found, key=lambda t: str(t[0].get("startedAt"))):
    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None
    nz = o("Normalize") or {}
    raw = o("Webhook") or {}
    raw = raw.get("body", raw)
    ld = nz.get("lead") or {}
    camp = nz.get("campaign") or {}
    cs = o("M7 Critical Slack") or {}
    gate = o("M7 Alert Gate") or {}
    ps = o("M7 Person Search URL") or {}
    items = ((ps.get("data") or {}) or {}).get("items") or []
    print(f"\n  exec {r['id']}  {r.get('startedAt')}  status={r.get('status')}")
    print(f"     event      : {nz.get('event')!r}")
    print(f"     lead       : {ld.get('full_name')!r}  slug={ld.get('slug')!r}")
    print(f"     email      : {ld.get('email_address')!r}/{ld.get('enriched_email')!r}")
    print(f"     CAMPAIGN   : name={camp.get('name')!r}  id={camp.get('id')!r}")
    print(f"     raw campaign field: {json.dumps(raw.get('campaign'), ensure_ascii=False)[:110]}")
    print(f"     sender     : {(nz.get('sender') or {}).get('full_name')!r}")
    print(f"     PersonSearchURL items={len(items)} -> "
          f"{[(i.get('item') or {}).get('id') for i in items]}")
    print(f"     alert gate : should={gate.get('__should_alert')} "
          f"reason={gate.get('__alert_reason')!r} key={str(gate.get('__alert_key'))[-16:]!r}")
    print(f"     posted     : ok={cs.get('ok')} channel={cs.get('channel')}")
    txt = ((cs.get("message") or {}).get("text")) or ""
    if txt:
        print(f"     text       : {txt.splitlines()[0][:110]}")
    print(f"     nodes ran  : {len(rd)}")

print("\n" + "=" * 78)
print(f"14-DAY CENSUS of #lead-processing alerts (since {CUT[:10]})")
print("=" * 78)
nocamp = [a for a in alerts if not a["campaign"]]
print(f"  total delivered      : {len(alerts)}")
print(f"  campaign-sourced     : {len(alerts) - len(nocamp)}")
print(f"  MANUAL (no campaign) : {len(nocamp)}   "
      f"= {round(100 * len(nocamp) / max(1, len(alerts)))}% of the channel")
for a in sorted(nocamp, key=lambda x: str(x["at"]), reverse=True):
    print(f"     {str(a['at'])[:16]}  {str(a['lead'])[:30]}")
print("\n  by campaign:")
for k, v in Counter(str(a["campaign"])[:48] for a in alerts).most_common():
    print(f"     {v:>3}  {k}")
