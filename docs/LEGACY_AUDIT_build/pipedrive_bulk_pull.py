#!/usr/bin/env python3
"""Legacy Audit — bulk Pipedrive pull (READ-ONLY). ONE continuous paginated walk instead of
per-email spot checks, per the Pipedrive budget rule (announce bulk windows, don't spam
/persons/search per-email at full-history scale).

Uses /api/v2 cursor pagination (proven, not the v1 500-row-horizon trap - memory:
pipedrive-list-read-horizon). Pulls:
  - ALL persons: id, name, primary_email, add_time, owner_id, custom_fields[F_CAMPAIGN]
  - ALL leads:   id, title, person_id, label_ids, add_time, custom fields[F_LEADCAMP]

Feeds:
  - Section B (created-side): email -> person_id index, for contacted-vs-created matching
  - Section C (duplicates):   name collision detection among persons with DIFFERENT emails
  - Section D setup:          candidate record list for changelog sampling

Crash-safe: writes persons and leads to JSONL incrementally, resumable via next_cursor file.
"""
import json, os, ssl, time
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-audit/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")

THROTTLE_S = 0.15  # nobody contending tonight per Nik - still not zero


def pd_v2(path, params=None, tries=5):
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://api.pipedrive.com/api/v2{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1)); continue
            return {"__err": e.code, "__body": b}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def pd_v1(path, params=None, tries=5):
    # v2 has no /leads resource on this account (confirmed live: api.pipedrive.com/api/v2/leads
    # returns the web app's HTML, status 200, not JSON - v2 leads simply isn't exposed here).
    # v1 /leads DOES support proven start/limit pagination + explicit sort=add_time ASC
    # (additional_data.pagination.more_items_in_collection/next_start) - confirmed live, avoids
    # the unsorted-500-row-horizon trap (memory: pipedrive-list-read-horizon).
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1)); continue
            return {"__err": e.code, "__body": b}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def pull_persons_v2():
    out_path = os.path.join(EVID, "bulk_persons.jsonl")
    cursor_path = out_path + ".cursor"
    cursor = open(cursor_path, encoding="utf-8").read().strip() or None if os.path.exists(cursor_path) else None
    if cursor:
        print("resuming persons from saved cursor")
    mode = "a" if (cursor and os.path.exists(out_path)) else "w"
    total = 0
    t_start = time.time()
    with open(out_path, mode, encoding="utf-8") as f:
        page_n = 0
        while True:
            params = {"limit": 500}
            if cursor:
                params["cursor"] = cursor
            page = pd_v2("/persons", params)
            if page.get("__err"):
                print(f"  ERROR persons page {page_n}: {page.get('__err')} {page.get('__body','')[:200]}")
                break
            items = page.get("data") or []
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
            total += len(items)
            page_n += 1
            cursor = (page.get("additional_data") or {}).get("next_cursor")
            with open(cursor_path, "w", encoding="utf-8") as cf:
                cf.write(cursor or "")
            if page_n % 5 == 0 or not cursor:
                print(f"  persons: page {page_n}, {total} total so far ({time.time()-t_start:.0f}s)", flush=True)
            if not cursor or not items:
                break
            time.sleep(THROTTLE_S)
    if cursor is None and os.path.exists(cursor_path):
        os.remove(cursor_path)
    print(f"persons: DONE, {total} records -> {out_path}")
    return total


def pull_leads_v1():
    out_path = os.path.join(EVID, "bulk_leads.jsonl")
    start_path = out_path + ".start"
    start = int(open(start_path, encoding="utf-8").read().strip() or "0") if os.path.exists(start_path) else 0
    if start:
        print(f"resuming leads from saved start={start}")
    mode = "a" if start else "w"
    total = start
    t_start = time.time()
    with open(out_path, mode, encoding="utf-8") as f:
        page_n = 0
        while True:
            page = pd_v1("/leads", {"start": start, "limit": 500, "sort": "add_time ASC"})
            if page.get("__err"):
                print(f"  ERROR leads page {page_n}: {page.get('__err')} {page.get('__body','')[:200]}")
                break
            items = page.get("data") or []
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False, default=str) + "\n")
            total += len(items)
            page_n += 1
            pag = (page.get("additional_data") or {}).get("pagination") or {}
            more = pag.get("more_items_in_collection")
            start = pag.get("next_start", start + 500)
            with open(start_path, "w", encoding="utf-8") as sf:
                sf.write(str(start))
            if page_n % 5 == 0 or not more:
                print(f"  leads: page {page_n}, {total} total so far ({time.time()-t_start:.0f}s)", flush=True)
            if not more or not items:
                break
            time.sleep(THROTTLE_S)
    if not more and os.path.exists(start_path):
        os.remove(start_path)
    print(f"leads: DONE, {total} records -> {out_path}")
    return total


def main():
    print("=== bulk pull: persons (v2, cursor) ===")
    n_persons = pull_persons_v2()
    print("\n=== bulk pull: leads (v1, start/limit, sort=add_time ASC) ===")
    n_leads = pull_leads_v1()
    print(f"\nCOMPLETE. persons={n_persons} leads={n_leads}")


if __name__ == "__main__":
    main()
