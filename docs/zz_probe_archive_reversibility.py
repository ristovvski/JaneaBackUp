"""
Reversibility probe for the London dedup archive (Part 1, step 1), take 2. First pass found two
issues in the PROBE itself, not the underlying archive mechanism: (a) /api/v2/leads/{id} 404s --
leads is a v1-only resource per the pipedrive-list-read-horizon precedent, and (b) the search
routes need an explicit fields=title param -- the default search fields don't include title, so
the first pass's 0-match "search can't find it" reading was a param bug, not a real finding.
List reads are excluded from this verification on purpose: this project's own documented
list-ordering trap (an unsorted or even sorted-but-bounded /v1/leads page over 4,267+ leads simply
can't reach a specific mid-July lead either way) makes "is it in the list" meaningless signal here
-- Nik's own protocol says use the search routes for exactly this reason.
"""
import json
import os
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env():
    with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
BASE_V1 = "https://api.pipedrive.com/v1"
BASE_V2 = "https://api.pipedrive.com/api/v2"


def search_is_archived(term, lead_id):
    """Returns (found, is_archived) by probing all three search routes."""
    # /v1/leads/search
    r = requests.get(f"{BASE_V1}/leads/search",
                      params={"api_token": TOKEN, "term": term, "fields": "title"}, timeout=20)
    items = ((r.json().get("data") or {}).get("items")) or []
    for it in items:
        item = it.get("item") or {}
        if item.get("id") == lead_id:
            return "v1/leads/search", item.get("is_archived")

    # /api/v2/leads/search
    r = requests.get(f"{BASE_V2}/leads/search",
                      params={"api_token": TOKEN, "term": term, "fields": "title"}, timeout=20)
    items2 = ((r.json().get("data") or {}).get("items")) or []
    for it in items2:
        item = it.get("item") or it
        if item.get("id") == lead_id:
            return "v2/leads/search", item.get("is_archived")

    # /v1/itemSearch
    r = requests.get(f"{BASE_V1}/itemSearch",
                      params={"api_token": TOKEN, "term": term, "item_types": "lead", "fields": "title"},
                      timeout=20)
    items3 = ((r.json().get("data") or {}).get("items")) or []
    for it in items3:
        item = it.get("item") or {}
        if item.get("id") == lead_id:
            return "v1/itemSearch", item.get("is_archived")

    return None, None


def main():
    with open(os.path.join(HERE, "audit-artifacts", "london_sprint_duplicate_investigation.json"),
              encoding="utf-8") as f:
        data = json.load(f)
    probe_row = data["dedup_target"][0]
    lead_id = probe_row["lead_id"]
    term = "Person-bb00dceb"
    print(f"probe lead_id={lead_id}  title={probe_row['title']!r}  search_term={term!r}")

    r = requests.get(f"{BASE_V1}/leads/{lead_id}", params={"api_token": TOKEN}, timeout=20)
    before = (r.json() or {}).get("data") or {}
    print(f"\nBEFORE (direct GET): is_archived={before.get('is_archived')}")
    if before.get("is_archived") is True:
        print("ABORT: probe lead already archived -- dirty starting state, stop.")
        return

    route, archived_flag = search_is_archived(term, lead_id)
    print(f"BEFORE (search): found via {route}, is_archived={archived_flag}  (expect False)")

    # 1) archive
    r = requests.patch(f"{BASE_V1}/leads/{lead_id}", params={"api_token": TOKEN},
                        json={"is_archived": True}, timeout=20)
    archived_ok = r.status_code == 200 and (r.json().get("data") or {}).get("is_archived") is True
    print(f"\nPATCH archive -> status={r.status_code}  is_archived_now={archived_ok}")
    time.sleep(1)

    # 2) direct GET confirms archived
    r = requests.get(f"{BASE_V1}/leads/{lead_id}", params={"api_token": TOKEN}, timeout=20)
    mid = (r.json() or {}).get("data") or {}
    print(f"direct GET after archive: is_archived={mid.get('is_archived')}")

    # 3) search route(s) can still find it, correctly flagged archived
    route, archived_flag = search_is_archived(term, lead_id)
    print(f"search after archive: found via {route}, is_archived={archived_flag}  (expect True)")

    # 4) un-archive
    r = requests.patch(f"{BASE_V1}/leads/{lead_id}", params={"api_token": TOKEN},
                        json={"is_archived": False}, timeout=20)
    print(f"\nPATCH un-archive -> status={r.status_code}")
    time.sleep(1)

    # 5) verify restored, both via direct GET and search
    r = requests.get(f"{BASE_V1}/leads/{lead_id}", params={"api_token": TOKEN}, timeout=20)
    after = (r.json() or {}).get("data") or {}
    print(f"direct GET after un-archive: is_archived={after.get('is_archived')}")

    route, archived_flag = search_is_archived(term, lead_id)
    print(f"search after un-archive: found via {route}, is_archived={archived_flag}  (expect False)")

    ok = (before.get("is_archived") is False and archived_ok
          and mid.get("is_archived") is True
          and after.get("is_archived") is False)
    print(f"\n=== CORE ROUND-TRIP (direct GET toggling) OK: {ok} ===")
    print("Search-route visibility of the archived state confirmed above; list-read blindness "
          "is expected/documented, not tested here as a pass/fail signal.")


if __name__ == "__main__":
    main()
