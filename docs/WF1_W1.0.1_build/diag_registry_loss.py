#!/usr/bin/env python3
"""Did WF-1's alert registry LOSE writes? Test it without guessing.

Every alerting execution reports __alert_registry_size as it read the store. If writes were durable
the size would rise monotonically, roughly once per delivered alert. Compare the observed sizes
against the count of delivered alerts over the same window - a shortfall is lost updates, which is
the documented staticData whole-object clobber (113 claims, 2026-08-11).
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
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


rows, cur, pages = [], None, 0
while pages < 6:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    ex = d.get("data") or []
    if not ex:
        break
    for r in ex:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "M7 Alert Gate" not in rd:
            continue

        def o(nm):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"]
            except Exception:
                return None

        g = o("M7 Alert Gate") or {}
        cs = o("M7 Critical Slack") or {}
        rows.append({"exec": r["id"], "at": r.get("startedAt"),
                     "size": g.get("__alert_registry_size"),
                     "key": g.get("__alert_key"),
                     "should": g.get("__should_alert"),
                     "reason": g.get("__alert_reason"),
                     "posted": cs.get("ok") is True and cs.get("channel") == TEAM,
                     "pruned": g.get("__alert_pruned")})
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break

rows = [r for r in rows if r["size"] is not None]
rows.sort(key=lambda r: str(r["at"]))
print(f"alerting executions with a registry reading: {len(rows)}\n")
print("  time                 exec    size  pruned  should  reason            posted  key")
prev = None
drops = []
for r in rows[-28:]:
    d = ""
    if prev is not None and r["size"] < prev:
        d = f"   <<< DROPPED {prev}->{r['size']}"
        drops.append((prev, r["size"], r["at"]))
    print(f"  {str(r['at'])[:19]}  {r['exec']:<6} {str(r['size']):>4}  "
          f"{str(r['pruned']):>6}  {str(r['should']):<6}  {str(r['reason'])[:16]:<16}  "
          f"{str(r['posted']):<6}  {str(r['key'])[:22]}{d}")
    prev = r["size"]

delivered = [r for r in rows if r["posted"]]
first_alerts = [r for r in rows if r["reason"] == "first_alert"]
dupes = {}
for r in first_alerts:
    dupes.setdefault(r["key"], []).append(r["at"])
repeat = {k: v for k, v in dupes.items() if k and len(v) > 1}

print(f"\n  delivered alerts in window     : {len(delivered)}")
print(f"  'first_alert' decisions        : {len(first_alerts)}")
print(f"  KEYS THAT GOT 'first_alert' MORE THAN ONCE: {len(repeat)}")
for k, v in list(repeat.items())[:8]:
    print(f"     {k:<24} x{len(v)}  {[str(t)[:16] for t in v]}")
print(f"\n  observed size DROPS (writes lost): {len(drops)}")
for a_, b_, t in drops[:6]:
    print(f"     {t[:19]}  {a_} -> {b_}")
