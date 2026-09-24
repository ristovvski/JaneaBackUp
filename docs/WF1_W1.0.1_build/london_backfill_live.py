#!/usr/bin/env python3
"""London Sales Sprint 2026 backfill — LIVE WRITE (WRITE_MODE=live required; default shadow).

Consumes DISCOVERY/london_backfill_dryrun_v2_output.json (215 rows, per-category treatment already
resolved — 9 bounce/departed, 4 OOO, 1 Not Interested, 201 standard cold, 0 left Uncategorized).
Re-verifies every row fresh immediately before writing — this run is gated on a race-condition fix
+ re-seed on the wire, and Pipedrive is shared concurrently with another session, so a stale gate
from the original dry-run (days old) is not trusted:

  GATE 1  Pipedrive existence re-check per row (/api/v2/persons/search, exact_match) — skip if a
          person for this email now exists (created by us since, or by the concurrent session).
  GATE 2  Smartlead is_unsubscribed re-check, ONE fresh pull of /campaigns/{id}/leads for both
          campaigns, done at the top of this run (not reused from the dry-run).
  GATE 3  Smartlead DNC-category re-check (lead_category_id against any category named
          "do not contact"), same fresh pull.

Per row that passes all three gates:
  1. POST /api/v2/persons  (person_body, verified contract — backfill_ai4_persons.py)
  2. POST /v1/leads        (lead_body + person_id, verified contract — backfill300_leads_and_owner_fix.py)
  3. if has_reply: POST /api/v2/activities (reply_activity_body + lead_id, verified contract —
     r1_reply_backfill.py). NO forward-email send for any of the 14 (explicit — a separate,
     never-given go). NO registry write attempted (no confirmed API path to dnc_registry_dev,
     and that table is owned by another session — hand off via file, never write to it directly).

Throttled: 0.6s sleep between Pipedrive writes (Pipedrive access is shared this run).
Rollback note: these are CREATES, not overwrites — "rollback" means deleting the created
person/lead/activity ids logged here, never a PUT-back of prior state.
"""
import json, os, ssl, sys, time
import urllib.request, urllib.parse

WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DISC = os.path.join(HERE, "..", "DISCOVERY")
EVID = os.path.join(HERE, "wf1-release-evidence")

THROTTLE_S = 0.6
CAMPS = {3565651: "[Sales Sprint] Sales Sprint 2026 – London – Catch-alls",
         3565502: "[Sales Sprint] Sales Sprint 2026 – London – Valids"}


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


def pd(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path, data=data, method=method,
                                       headers={"x-api-token": PDT, "User-Agent": UA,
                                                **({"Content-Type": "application/json"} if data else {})})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return e.code, b
    return 0, None


def pd_v1_search(email):
    q = urllib.parse.urlencode({"api_token": PDT, "term": email, "fields": "email",
                                 "exact_match": "true", "limit": 1})
    url = f"https://janeasystems.pipedrive.com/api/v1/persons/search?{q}"
    for i in range(4):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=45, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i + 1 < 4:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r}  ({'LIVE — WILL WRITE' if live else 'dry run, no writes'})")

    plan = json.load(open(os.path.join(DISC, "london_backfill_dryrun_v2_output.json"), encoding="utf-8"))
    rows = plan["rows"]
    print(f"input: {len(rows)} planned rows (with_reply: {sum(1 for r in rows if r.get('has_reply'))})")

    # fresh GATE 2/3 pull, right now — not reused from the (days-old) dry-run
    target_emails = {r["email"] for r in rows}
    unsub_map, category_map = {}, {}
    for cid in CAMPS:
        offset = 0
        while True:
            page = sl(f"/campaigns/{cid}/leads", {"offset": offset, "limit": 100})
            data = page.get("data") if isinstance(page, dict) else page
            if not data:
                break
            for r in data:
                lead = r.get("lead") or {}
                em = (lead.get("email") or "").lower()
                if em in target_emails:
                    unsub_map[em] = bool(lead.get("is_unsubscribed"))
                    category_map[em] = r.get("lead_category_id")
            if len(data) < 100:
                break
            offset += 100
    cats = sl("/leads/fetch-categories")
    cat_name_by_id = {c["id"]: c["name"] for c in (cats if isinstance(cats, list) else cats.get("data", []))}
    dnc_cat_ids = {cid for cid, name in cat_name_by_id.items() if "do not contact" in (name or "").lower()}
    print(f"fresh gate-2/3 data: {len(unsub_map)}/{len(target_emails)} emails covered; "
          f"dnc-named category ids: {dnc_cat_ids}")

    results = []
    counts = {"created": 0, "skip_now_exists": 0, "skip_unsubscribed": 0, "skip_dnc_category": 0, "failed": 0}
    by_treatment = {}

    for r in rows:
        email = r["email"]
        row_out = {"email": email, "treatment": r.get("treatment")}

        # GATE 1: fresh existence re-check, immediately before writing
        s = pd_v1_search(email)
        items = ((s or {}).get("data") or {}).get("items") or []
        if items:
            row_out["action"] = "skip_now_exists"
            row_out["existing_person_id"] = items[0]["item"]["id"]
            counts["skip_now_exists"] += 1
            print(f"  SKIP  {email:<38} now_exists (person {items[0]['item']['id']})")
            results.append(row_out)
            continue

        # GATE 2
        if unsub_map.get(email) is True:
            row_out["action"] = "skip_unsubscribed"
            counts["skip_unsubscribed"] += 1
            print(f"  SKIP  {email:<38} unsubscribed (fresh re-check)")
            results.append(row_out)
            continue

        # GATE 3
        if category_map.get(email) in dnc_cat_ids:
            row_out["action"] = "skip_dnc_category"
            row_out["category"] = cat_name_by_id.get(category_map.get(email))
            counts["skip_dnc_category"] += 1
            print(f"  SKIP  {email:<38} dnc_category ({row_out['category']})")
            results.append(row_out)
            continue

        if not live:
            row_out["action"] = "would_create"
            counts["created"] += 1
            by_treatment[r.get("treatment")] = by_treatment.get(r.get("treatment"), 0) + 1
            print(f"  WOULD_CREATE {email:<38} treatment={r.get('treatment')}")
            results.append(row_out)
            continue

        try:
            pst, presp = pd("/api/v2/persons", "POST", r["person_body"])
            if pst >= 300:
                raise RuntimeError(f"person create failed: {pst} {presp}")
            person_id = (presp.get("data") or {}).get("id")
            time.sleep(THROTTLE_S)

            lead_body = dict(r["lead_body"]); lead_body["person_id"] = person_id
            lst, lresp = pd("/v1/leads", "POST", lead_body)
            if lst >= 300:
                raise RuntimeError(f"lead create failed: {lst} {lresp}")
            lead_id = (lresp.get("data") or {}).get("id")
            time.sleep(THROTTLE_S)

            activity_id = None
            if r.get("has_reply"):
                abody = dict(r["reply_activity_body"]); abody["lead_id"] = lead_id
                ast_, aresp = pd("/api/v2/activities", "POST", abody)
                if ast_ >= 300:
                    raise RuntimeError(f"activity create failed: {ast_} {aresp}")
                activity_id = (aresp.get("data") or {}).get("id")
                time.sleep(THROTTLE_S)

            row_out.update({"action": "created", "person_id": person_id, "lead_id": lead_id,
                             "activity_id": activity_id})
            counts["created"] += 1
            by_treatment[r.get("treatment")] = by_treatment.get(r.get("treatment"), 0) + 1
            print(f"  CREATED {email:<38} person={person_id} lead={str(lead_id)[:8]} "
                  f"activity={activity_id} treatment={r.get('treatment')}")
        except Exception as e:  # noqa: BLE001
            row_out["action"] = "failed"
            row_out["error"] = str(e)[:300]
            counts["failed"] += 1
            print(f"  FAILED  {email:<38} {e}")

        results.append(row_out)

    print(f"\n=== SUMMARY ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  by_treatment: {by_treatment}")

    out_path = os.path.join(EVID, "london_backfill_live_log.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"write_mode": WRITE_MODE, "counts": counts, "by_treatment": by_treatment,
                    "rows": results}, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote {out_path}")
    if not live:
        print("\nDRY RUN COMPLETE — nothing was written. Re-run with WRITE_MODE=live to deploy.")


if __name__ == "__main__":
    main()
