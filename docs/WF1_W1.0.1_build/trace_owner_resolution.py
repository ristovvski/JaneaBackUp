#!/usr/bin/env python3
"""READ ONLY. Part 4: why did the lead land on Melisa Bahonjic, who left in July, when the campaign
sender is Noah?

Four things to establish, from the systems rather than from assumption:
  a. who the Pipedrive users are, which are deactivated, and which Melisa is which
  b. what WF-1 actually uses as `owner_id` - one configured constant, or a per-campaign /
     per-sender map
  c. the owner on THIS person and lead, and whether we set it or inherited it
  d. how many recent leads are landing on her - the blast radius
"""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
WF2 = "jp7rum9Z0YDJkQWv"
PERSON = 86369


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


print("=" * 78)
print("a. Pipedrive users - who is active, who is not")
print("=" * 78)
users = (pd("/v1/users") or {}).get("data") or []
print("  total users: %d" % len(users))
for u in sorted(users, key=lambda x: str(x.get("name"))):
    flag = "ACTIVE  " if u.get("active_flag") else "DISABLED"
    if not u.get("active_flag") or "melisa" in str(u.get("name")).lower() \
            or "noah" in str(u.get("name")).lower():
        print("  %-9s id=%-10s %-28s %s" % (flag, u.get("id"), str(u.get("name"))[:28],
                                            u.get("email")))

print("\n" + "=" * 78)
print("b. what WF-1 / WF-2 use as owner_id")
print("=" * 78)
for label, wid in (("WF-1", WF1), ("WF-2", WF2)):
    wf = n8n("/api/v1/workflows/%s" % wid)
    N = {n["name"]: n for n in wf["nodes"]}
    cfg = N.get("CONFIG")
    vals = {}
    if cfg:
        p = cfg.get("parameters") or {}
        for a in ((p.get("assignments") or {}).get("assignments")
                  or (p.get("fields") or {}).get("values") or []):
            vals[a.get("name")] = a.get("value")
    owner_keys = {k: v for k, v in vals.items()
                  if "owner" in str(k).lower() or "user" in str(k).lower()
                  or "sender" in str(k).lower()}
    print("\n  %s CONFIG owner-ish keys: %s" % (label, json.dumps(owner_keys,
                                                                  ensure_ascii=False)[:500]))
    hits = []
    for n in wf["nodes"]:
        blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
        if "owner_id" in blob:
            found = sorted(set(re.findall(r'owner_id["\']?\s*:\s*([^,}\n]{0,60})', blob)))
            hits.append((n["name"], found))
    print("  %s nodes that set owner_id:" % label)
    for nm, found in hits:
        print("     %-28s %s" % (nm[:28], json.dumps(found, ensure_ascii=False)[:180]))
    # is there ANY per-campaign or per-sender owner mapping anywhere?
    full = json.dumps(wf, ensure_ascii=False)
    for token in ("owner_map", "ownerMap", "sender_to_owner", "campaign_owner", "inbox_owner"):
        if token in full:
            print("     !! contains %r" % token)

print("\n" + "=" * 78)
print("c. the owner on THIS person and lead")
print("=" * 78)
p = (pd("/api/v2/persons/%d" % PERSON) or {}).get("data") or {}
print("  person %d %r  owner=%s  add_time=%s" % (PERSON, p.get("name"),
                                                 (p.get("owner") or {}).get("id"),
                                                 p.get("add_time")))
leads = (pd("/v1/leads?limit=50&person_id=%d" % PERSON) or {}).get("data") or []
umap = {u["id"]: u.get("name") for u in users}
for l in leads:
    print("  lead %s owner_id=%s (%s) creator=%s add_time=%s"
          % (l.get("id"), l.get("owner_id"), umap.get(l.get("owner_id")),
             l.get("creator_id"), l.get("add_time")))
    print("       title=%r" % str(l.get("title"))[:70])

print("\n" + "=" * 78)
print("d. blast radius - recent leads by owner")
print("=" * 78)
print("  NOTE: /v1/leads list is a ~7-day horizon and ignores archived_status, so this is")
print("  'recent, non-archived' by construction - it is a rate, not a total.")
rows, start = [], 0
while start < 2000:
    d = pd("/v1/leads?limit=500&start=%d" % start)
    got = (d or {}).get("data") or []
    rows += got
    more = (((d or {}).get("additional_data") or {}).get("pagination") or {}) \
        .get("more_items_in_collection")
    if not more or not got:
        break
    start += 500
print("  leads read: %d" % len(rows))
by_owner = Counter(l.get("owner_id") for l in rows)
print("  by owner:")
for oid, c in by_owner.most_common(12):
    u = umap.get(oid, "?")
    act = next((x.get("active_flag") for x in users if x.get("id") == oid), None)
    print("     %-10s %-26s %-9s %d" % (oid, str(u)[:26],
                                        "ACTIVE" if act else "DISABLED", c))
mel = [u for u in users if "melisa" in str(u.get("name")).lower()]
for m in mel:
    mine = [l for l in rows if l.get("owner_id") == m["id"]]
    print("\n  %s (id=%s, active=%s): %d recent leads" % (m.get("name"), m["id"],
                                                          m.get("active_flag"), len(mine)))
    for l in sorted(mine, key=lambda x: str(x.get("add_time")), reverse=True)[:8]:
        print("     %s  %r" % (str(l.get("add_time"))[:19], str(l.get("title"))[:62]))

with open(os.path.join(HERE, "trace_owner_resolution.json"), "w", encoding="utf-8") as f:
    json.dump({"users": [{k: u.get(k) for k in ("id", "name", "email", "active_flag")}
                         for u in users],
               "person_owner": (p.get("owner") or {}).get("id"),
               "leads": leads, "by_owner": dict(by_owner), "leads_read": len(rows)}, f,
              ensure_ascii=False, indent=1, default=str)
print("\n-> trace_owner_resolution.json")
