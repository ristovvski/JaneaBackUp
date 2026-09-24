"""READ-ONLY: pull ALL Pipedrive leads (sort=add_time DESC, archived_status=all) and keep any
whose title OR lead-Campaign field mentions ai4/sprint/london (case-insensitive). Broader net than
the earlier Ai4-only pull, reusable for the Sales Sprint reconciliation."""
import json, os, ssl, sys
import urllib.request, urllib.parse

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"


def pd(path, params=None, tries=4):
    import time
    q = dict(params or {}); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 janea-forensics/1.0"})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


TERMS = ("ai4", "sprint", "london")


def matches(ld):
    title = (ld.get("title") or "").lower()
    camp = str(ld.get(F_LEADCAMP) or "").lower()
    return any(t in title or t in camp for t in TERMS)


kept = []
start = 0
pages = 0
total_seen = 0
while True:
    page = pd("/leads", {"start": start, "limit": 500, "sort": "add_time DESC", "archived_status": "all"})
    if "__err" in page:
        print("ERROR:", page); break
    rows = page.get("data") or []
    if not rows:
        break
    total_seen += len(rows)
    kept.extend(l for l in rows if matches(l))
    pages += 1
    ad = (page.get("additional_data") or {}).get("pagination") or {}
    if not ad.get("more_items_in_collection"):
        break
    start = ad.get("next_start") or (start + len(rows))
    if pages % 20 == 0:
        print(f"...{pages} pages, {total_seen} leads seen, {len(kept)} kept")

print(f"TOTAL leads scanned: {pages} pages, {total_seen} leads. Kept (ai4/sprint/london): {len(kept)}")
with open(os.path.join(HERE, "sprint_all_leads_raw.jsonl"), "w", encoding="utf-8") as f:
    for l in kept:
        f.write(json.dumps(l, default=str) + "\n")
print("wrote sprint_all_leads_raw.jsonl")
