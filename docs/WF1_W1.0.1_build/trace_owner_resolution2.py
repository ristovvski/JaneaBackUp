#!/usr/bin/env python3
"""READ ONLY. Part 4, corrected pass.

The first pass produced two results that contradict the premise, so both need nailing down before
anything is claimed:

  * the lead is owned by **Noah**, not Melisa - so whatever shows Melisa is a different object
  * Melisa Bahonjic is **active_flag: true** in Pipedrive

and one result of MINE that was wrong: I grouped 2,000 leads by owner and called them "recent".
The sample came back with add_time 2025-02-03, so that read is not a recency window at all. Counting
by date here instead.

Three things:
  a. WF-1 CONFIG in full - what is `melisa_user_id` actually SET to?
  b. every activity on this lead and who owns it (the likely source of "owner is Melisa")
  c. leads created in the last N days, by owner, filtered on add_time rather than assumed
"""
import json
import os
import ssl
import sys
import time
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
LEAD = "987d0600-ac44-11f1-926c-6949d156b78a"
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
        return {"__err": "HTTP %s" % e.code}
    except Exception as e:
        if a < 3:
            time.sleep(3)
            return pd(p, a + 1)
        return {"__err": str(e)[:120]}


users = {u["id"]: u for u in ((pd("/v1/users") or {}).get("data") or [])}

print("=" * 78)
print("a. WF-1 CONFIG - the actual value behind `melisa_user_id`")
print("=" * 78)
wf = n8n("/api/v1/workflows/%s" % WF1)
N = {n["name"]: n for n in wf["nodes"]}
cfg = N.get("CONFIG")
p = cfg.get("parameters") or {}
print("  CONFIG node type=%s tv=%s  param keys=%s"
      % (cfg["type"].split(".")[-1], cfg.get("typeVersion"), sorted(p.keys())))
vals = {}
for shape in (((p.get("assignments") or {}).get("assignments") or []),
              ((p.get("fields") or {}).get("values") or []),
              (p.get("values") or {}).get("number", []) if isinstance(p.get("values"), dict) else []):
    for a in shape:
        if isinstance(a, dict) and a.get("name") is not None:
            vals[a["name"]] = a.get("value")
if not vals and p.get("jsCode"):
    print("  CONFIG is a CODE node; scanning its source for the key")
    src = p["jsCode"]
    import re
    for m in re.finditer(r"(melisa_user_id|owner_id)\s*:\s*([^,\n}]+)", src):
        print("     %s = %s" % (m.group(1), m.group(2).strip()))
for k, v in sorted(vals.items()):
    if "user" in k.lower() or "owner" in k.lower() or "melisa" in k.lower():
        who = users.get(v, {}).get("name") if isinstance(v, int) else None
        print("     %-26s = %r   %s" % (k, v, ("-> " + str(who)) if who else ""))

print("\n" + "=" * 78)
print("b. activities on the lead - who owns them")
print("=" * 78)
acts = (pd("/api/v2/activities?limit=50&lead_id=%s" % LEAD) or {}).get("data") or []
print("  activities on lead %s: %d" % (LEAD[:18], len(acts)))
for a in acts:
    oid = a.get("owner_id")
    print("     id=%-7s %-10s owner=%-10s (%-18s) %r"
          % (a.get("id"), a.get("type"), oid, str(users.get(oid, {}).get("name"))[:18],
             str(a.get("subject"))[:44]))
lead = (pd("/v1/leads/%s" % LEAD) or {}).get("data") or {}
print("  LEAD owner_id=%s (%s)  creator_id=%s (%s)"
      % (lead.get("owner_id"), users.get(lead.get("owner_id"), {}).get("name"),
         lead.get("creator_id"), users.get(lead.get("creator_id"), {}).get("name")))

print("\n" + "=" * 78)
print("c. leads created in the last %d days, by owner (filtered on add_time, not assumed)" % DAYS)
print("=" * 78)
cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
rows, start, pages = [], 0, 0
while pages < 40:
    d = pd("/v1/leads?limit=500&start=%d" % start)
    got = (d or {}).get("data") or []
    rows += got
    pages += 1
    more = (((d or {}).get("additional_data") or {}).get("pagination") or {}) \
        .get("more_items_in_collection")
    if not more or not got:
        break
    start += 500
print("  pages walked: %d   leads read: %d" % (pages, len(rows)))


def added(l):
    t = str(l.get("add_time") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


dated = [(l, added(l)) for l in rows]
undated = sum(1 for _, d in dated if d is None)
recent = [l for l, d in dated if d and d >= cutoff]
oldest = min((d for _, d in dated if d), default=None)
newest = max((d for _, d in dated if d), default=None)
print("  add_time range in the read: %s -> %s   (unparseable: %d)"
      % (str(oldest)[:19], str(newest)[:19], undated))
print("  leads created in the last %d days: %d" % (DAYS, len(recent)))
c = Counter(l.get("owner_id") for l in recent)
for oid, n in c.most_common(10):
    u = users.get(oid, {})
    print("     %-10s %-24s active=%-5s %d" % (oid, str(u.get("name"))[:24],
                                               u.get("active_flag"), n))
mel = [uid for uid, u in users.items() if "melisa" in str(u.get("name")).lower()]
for m in mel:
    mine = [l for l in recent if l.get("owner_id") == m]
    print("\n  %s (id=%s): %d leads in the last %d days"
          % (users[m].get("name"), m, len(mine), DAYS))
    for l in sorted(mine, key=lambda x: str(x.get("add_time")), reverse=True)[:10]:
        print("     %s  %r" % (str(l.get("add_time"))[:19], str(l.get("title"))[:60]))

with open(os.path.join(HERE, "trace_owner_resolution2.json"), "w", encoding="utf-8") as f:
    json.dump({"config_values": {k: v for k, v in vals.items()},
               "lead": lead, "activities": acts,
               "days": DAYS, "leads_read": len(rows), "recent": len(recent),
               "by_owner_recent": {str(k): v for k, v in c.items()}}, f,
              ensure_ascii=False, indent=1, default=str)
print("\n-> trace_owner_resolution2.json")
