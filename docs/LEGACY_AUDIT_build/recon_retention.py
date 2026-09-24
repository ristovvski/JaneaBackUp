#!/usr/bin/env python3
"""Legacy Systems Audit — Step 0 recon (READ-ONLY).
Establishes per-source retention horizon + full historical campaign inventory,
since every later section (A-F) depends on knowing what's even measurable.

Known landmines from prior sessions (memory), deliberately avoided here:
  - pipedrive-list-read-horizon: an uncapped-looking /v1/leads 500-row pull is actually a
    ~7-day horizon in practice; must page explicitly and check total counts via v2 pagination.
  - pipedrive-list-ordering-trap: any /v1 list read used for counting must prove its sort order;
    unsorted returns the OLDEST page, not the newest (opposite of what "recent" queries expect).
  - smartlead-list-ordering-trap: /statistics defaults to the OLDEST 500 rows; leads-statistics
    caps limit at 100 - must paginate with hasMore, never trust a single unpaginated pull.
"""
import json, os, ssl, time
import urllib.request, urllib.parse

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
HRK = os.environ["HEYREACH_API_KEY"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
MAKE_TOKEN = os.environ.get("MAKE_API_TOKEN", "")
MAKE_ZONE = os.environ.get("MAKE_ZONE", "")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-audit/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))


def sl(path, params=None, tries=4):
    q = dict(params or {}); q["api_key"] = SLK
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def hr(path, body=None, tries=4):
    data = json.dumps(body or {}).encode()
    for i in range(tries):
        try:
            r = urllib.request.Request(f"https://api.heyreach.io/api/public{path}", data=data, method="POST",
                                       headers={"X-API-KEY": HRK, "accept": "application/json",
                                                "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def pd_v1(path, params=None, tries=4):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def n8n(path, params=None, tries=4):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def make_api(path, params=None, tries=4):
    if not MAKE_TOKEN:
        return {"__err": "no MAKE_API_TOKEN"}
    q = dict(params or {})
    url = f"https://{MAKE_ZONE}.make.com/api/v2{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"Authorization": f"Token {MAKE_TOKEN}", "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4); continue
            return {"__err": e.code, "__body": b}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def main():
    out = {}

    print("=" * 90); print("N8N — execution retention horizon"); print("=" * 90)
    first_page = n8n("/api/v1/executions", {"limit": 250})
    all_execs = list(first_page.get("data", []))
    cursor = first_page.get("nextCursor")
    pages = 1
    while cursor and pages < 20:
        page = n8n("/api/v1/executions", {"limit": 250, "cursor": cursor})
        all_execs.extend(page.get("data", []))
        cursor = page.get("nextCursor")
        pages += 1
    if all_execs:
        starts = [e.get("startedAt") for e in all_execs if e.get("startedAt")]
        print(f"  paged {pages} pages, {len(all_execs)} executions total")
        print(f"  newest startedAt: {max(starts)}")
        print(f"  oldest startedAt: {min(starts)}   <-- retention horizon")
    out["n8n"] = {"total_paged": len(all_execs), "pages": pages,
                  "oldest": min(starts) if all_execs else None, "newest": max(starts) if all_execs else None}

    print("\n" + "=" * 90); print("SMARTLEAD — full campaign inventory"); print("=" * 90)
    camps = sl("/campaigns")
    camps = camps if isinstance(camps, list) else camps.get("data", [])
    print(f"  total campaigns: {len(camps)}")
    if camps:
        created = sorted(c.get("created_at", "") for c in camps if c.get("created_at"))
        print(f"  earliest campaign created_at: {created[0] if created else 'n/a'}")
        print(f"  latest   campaign created_at: {created[-1] if created else 'n/a'}")
    out["smartlead"] = {"campaign_count": len(camps),
                        "campaigns": [{"id": c.get("id"), "name": c.get("name"),
                                       "created_at": c.get("created_at"), "status": c.get("status")}
                                      for c in camps]}

    print("\n" + "=" * 90); print("HEYREACH — full campaign inventory"); print("=" * 90)
    hr_camps = []
    offset = 0
    while True:
        page = hr("/campaign/GetAll", {"offset": offset, "limit": 100})
        items = page.get("items") if isinstance(page, dict) else None
        if not items:
            break
        hr_camps.extend(items)
        if len(items) < 100:
            break
        offset += 100
    print(f"  total campaigns: {len(hr_camps)}")
    if hr_camps:
        created = sorted(c.get("creationTime", "") for c in hr_camps if c.get("creationTime"))
        print(f"  earliest campaign creationTime: {created[0] if created else 'n/a'}")
        print(f"  latest   campaign creationTime: {created[-1] if created else 'n/a'}")
    out["heyreach"] = {"campaign_count": len(hr_camps),
                       "campaigns": [{"id": c.get("id"), "name": c.get("name"),
                                      "creationTime": c.get("creationTime"), "status": c.get("status")}
                                     for c in hr_camps]}

    print("\n" + "=" * 90); print("PIPEDRIVE — earliest person/lead (v1 sort=add_time ASC, proven ordering)"); print("=" * 90)
    earliest_person = pd_v1("/persons", {"sort": "add_time ASC", "limit": 1})
    earliest_lead = pd_v1("/leads", {"sort": "add_time ASC", "limit": 1})
    ep = ((earliest_person or {}).get("data") or [{}])
    el = ((earliest_lead or {}).get("data") or [{}])
    ep0 = ep[0] if ep else {}
    el0 = el[0] if el else {}
    print(f"  earliest person add_time: {ep0.get('add_time')}  (id {ep0.get('id')})")
    print(f"  earliest lead   add_time: {el0.get('add_time')}  (id {el0.get('id')})")
    changelog_test = pd_v1(f"/persons/{ep0.get('id')}/changelog") if ep0.get("id") else {}
    cl_items = (changelog_test.get("data") or [])
    print(f"  changelog depth check on earliest person: {len(cl_items)} entries "
          f"(oldest: {cl_items[-1].get('time') if cl_items else 'n/a'})")
    out["pipedrive"] = {"earliest_person_add_time": ep0.get("add_time"), "earliest_person_id": ep0.get("id"),
                        "earliest_lead_add_time": el0.get("add_time"), "earliest_lead_id": el0.get("id"),
                        "changelog_entries_on_earliest_person": len(cl_items)}

    print("\n" + "=" * 90); print("MAKE — scenario/log retention probe"); print("=" * 90)
    scenarios = make_api("/scenarios", {"teamId": ""}) if MAKE_TOKEN else {"__err": "skipped, need teamId"}
    print(f"  /scenarios probe: {json.dumps(scenarios)[:300]}")
    out["make"] = {"scenarios_probe": scenarios if not isinstance(scenarios, dict) or len(json.dumps(scenarios)) < 2000 else "large-response-truncated"}

    with open(os.path.join(HERE, "evidence", "step0_retention_recon.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote evidence/step0_retention_recon.json")


if __name__ == "__main__":
    main()
