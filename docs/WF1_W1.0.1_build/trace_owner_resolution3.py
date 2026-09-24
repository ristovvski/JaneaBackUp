#!/usr/bin/env python3
"""READ ONLY. Part 4, third pass - two corrections to my own method.

1. WF-1's CONFIG is a Set node in `jsonOutput` mode, so both of my parameter shapes missed it.
   Parse the JSON blob and read `melisa_user_id` directly.
2. My "recent leads by owner" read was worthless: 40 pages / 20,000 rows of `/v1/leads` came back
   spanning 2023-05 to 2025-07 with **zero** in the last 14 days. That is the list-ordering trap
   exactly as recorded - an unsorted /v1 list read returns the OLDEST page first. Re-do it with an
   explicit sort and PROVE the ordering before counting anything.
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 14


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        raise


def pd(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": "HTTP %s" % e.code, "__code": e.code}
    except Exception as e:
        if a < 3:
            time.sleep(3)
            return pd(p, a + 1)
        return {"__err": str(e)[:120]}


users = {u["id"]: u for u in ((pd("/v1/users") or {}).get("data") or [])}

print("=" * 78)
print("1. WF-1 CONFIG (Set node, jsonOutput mode)")
print("=" * 78)
wf = n8n("/api/v1/workflows/%s" % WF1)
cfg = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
raw = (cfg.get("parameters") or {}).get("jsonOutput")
blob = raw
if isinstance(raw, str):
    try:
        blob = json.loads(raw.lstrip("=").strip())
    except Exception:
        blob = None
if isinstance(blob, dict):
    for k, v in sorted(blob.items()):
        if any(t in k.lower() for t in ("user", "owner", "melisa", "channel", "campaign")):
            who = users.get(v, {}).get("name") if isinstance(v, int) else None
            print("  %-28s = %r %s" % (k, v, ("-> " + str(who)) if who else ""))
    mu = blob.get("melisa_user_id")
    print("\n  >>> melisa_user_id = %r  -> %s (active=%s)"
          % (mu, users.get(mu, {}).get("name"), users.get(mu, {}).get("active_flag")))
else:
    print("  could not parse jsonOutput; raw head: %s" % str(raw)[:400])

print("\n" + "=" * 78)
print("2. recent leads by owner - with the ordering PROVEN, not assumed")
print("=" * 78)
cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)


def parse(t):
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(t), fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


order_ok, rows = False, []
for sort in ("add_time DESC", "add_time%20DESC", "-add_time"):
    q = "/v1/leads?limit=100&sort=" + urllib.parse.quote(sort, safe="%")
    d = pd(q)
    got = (d or {}).get("data") or []
    if not got:
        print("  sort=%-16r -> %s" % (sort, str(d)[:110]))
        continue
    first, last = parse(got[0].get("add_time")), parse(got[-1].get("add_time"))
    desc = bool(first and last and first >= last)
    fresh = bool(first and first >= cutoff)
    print("  sort=%-16r -> %d rows, first=%s last=%s  descending=%s recent=%s"
          % (sort, len(got), str(first)[:19], str(last)[:19], desc, fresh))
    if desc and fresh:
        order_ok, rows, chosen = True, got, sort
        break

if not order_ok:
    print("\n  NO ordering could be proven on /v1/leads. Refusing to count from it - an unsorted")
    print("  read returns the OLDEST page, which is how the previous pass produced 20,000 leads")
    print("  from 2023-2025 and zero from this fortnight.")
    print("  Falling back to the ACTIVITY surface, which is what actually carries the owner here.")
else:
    page, start = list(rows), len(rows)
    while start < 5000:
        d = pd("/v1/leads?limit=100&start=%d&sort=%s"
               % (start, urllib.parse.quote(chosen, safe="%")))
        got = (d or {}).get("data") or []
        if not got:
            break
        page += got
        oldest = parse(got[-1].get("add_time"))
        if oldest and oldest < cutoff:
            break
        start += 100
    recent = [l for l in page if (parse(l.get("add_time")) or datetime.min.replace(
        tzinfo=timezone.utc)) >= cutoff]
    print("\n  rows walked: %d   created in the last %d days: %d" % (len(page), DAYS, len(recent)))
    c = Counter(l.get("owner_id") for l in recent)
    for oid, n in c.most_common(10):
        u = users.get(oid, {})
        print("     %-10s %-24s active=%-5s %d" % (oid, str(u.get("name"))[:24],
                                                   u.get("active_flag"), n))

print("\n" + "=" * 78)
print("3. the surface that actually carries Melisa - ACTIVITIES we created, last %d days" % DAYS)
print("=" * 78)
since = cutoff.strftime("%Y-%m-%d")
acts, cur = [], 0
while cur < 4000:
    d = pd("/api/v2/activities?limit=500&cursor=%s" % cur if False else
           "/api/v2/activities?limit=500&updated_since=%sT00:00:00Z" % since)
    got = (d or {}).get("data") or []
    acts += got
    nxt = ((d or {}).get("additional_data") or {}).get("next_cursor")
    if not nxt:
        break
    cur += 500
print("  activities updated since %s: %d" % (since, len(acts)))
byo = Counter(a.get("owner_id") for a in acts)
for oid, n in byo.most_common(8):
    u = users.get(oid, {})
    print("     %-10s %-24s active=%-5s %d" % (oid, str(u.get("name"))[:24],
                                               u.get("active_flag"), n))
