#!/usr/bin/env python3
"""London Sales Sprint 2026 backfill — DRY RUN ONLY. Never writes to Pipedrive or Smartlead;
computes and reports intended writes. Reuses the Ai4 backfill machinery:
- person body mirrors backfill_ai4_persons.py's build_person()
- lead body mirrors backfill300_leads_and_owner_fix.py's convention
- reply-priority treatment (labels, activity, forward target) mirrors WF-2's OWN verified code
  (Body Lead Labels Union, Body Reply Activity, Forward Resolve) pulled live from the workflow.

Per-row gates before a row counts as "would create":
  1. Fresh Pipedrive existence re-check (person still absent as of NOW)
  2. Smartlead is_unsubscribed re-check (fresh, from /campaigns/{id}/leads)
  3. Smartlead lead_category re-check: any category containing "do not contact" -> excluded

Forward-email (a REAL external send via Smartlead, not a CRM write) is computed and reported
SEPARATELY, never included in any live pass here — needs its own explicit go.
"""
import json, os, ssl, time
import urllib.request, urllib.parse

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DISC = os.path.join(HERE, "..", "DISCOVERY")

MELISA = 16340280
CHANNEL = 578
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"

F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"
OPP_VALUE = 480
F_CAMPAIGN = "86157bb49563191c17b4dc62580525f84417524c"
F_HYPO = "8bdae1a91272e92b335e9e99f668cde659b6daae"
F_MEDIUM = "961698945b0329b367da11916a94f10ff7ba71fe"
F_SOURCE = "6070ae31f09228f95048b0f68982b1cd4d3a684a"
SOURCE_EMAIL = 446
MEDIUM_EMAIL = "eMail"
HYPOTHESIS_VALUE = "Sales Sprint"   # verified live against ~5,170 existing London-sprint persons
# Event name deliberately NOT set: verified 5,169/5,170 existing Sales Sprint persons have it
# empty - this campaign family isn't a conference, the field doesn't apply.

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


def pd(path, params=None, tries=4):
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


def omit(d):
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def main():
    missing = json.load(open(os.path.join(DISC, "sprint_london_missing.json"), encoding="utf-8"))
    rows = missing["missing"]
    print(f"input: {len(rows)} candidate rows from sprint_london_missing.json")
    target_emails = set(r["email"] for r in rows)

    # 1) fresh /campaigns/{id}/leads pull -> is_unsubscribed + category, keyed by email
    unsub_map = {}
    category_map = {}
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
    print(f"fresh unsubscribe/category data pulled for {len(unsub_map)} of {len(target_emails)} target emails")

    # 2) categories lookup (id -> name) to check for "do not contact" by name, not by guessed id
    cats = sl("/leads/fetch-categories")
    cat_name_by_id = {c["id"]: c["name"] for c in (cats if isinstance(cats, list) else cats.get("data", []))}
    dnc_cat_ids = {cid for cid, name in cat_name_by_id.items() if "do not contact" in (name or "").lower()}
    print(f"DNC-named category ids: {dnc_cat_ids}")

    excluded_now_exists = excluded_unsub = excluded_dnc_cat = 0
    to_create = []
    results = []
    for r in rows:
        email = r["email"]
        cid = r["campaign_id"]
        camp_name = CAMPS[cid]

        # GATE 1: fresh Pipedrive existence re-check
        s = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true", "limit": 1})
        items = ((s or {}).get("data") or {}).get("items") or []
        if items:
            excluded_now_exists += 1
            results.append({"email": email, "action": "skip_now_exists", "person_id": items[0]["item"]["id"]})
            continue

        # GATE 2: unsubscribed
        if unsub_map.get(email) is True:
            excluded_unsub += 1
            results.append({"email": email, "action": "skip_unsubscribed"})
            continue

        # GATE 3: DNC category
        if category_map.get(email) in dnc_cat_ids:
            excluded_dnc_cat += 1
            results.append({"email": email, "action": "skip_dnc_category",
                             "category": cat_name_by_id.get(category_map.get(email))})
            continue

        name = email.split("@")[0]
        person_body = {"name": name, "emails": [{"value": email, "primary": True, "label": "work"}],
                       "owner_id": MELISA,
                       "custom_fields": omit({F_CAMPAIGN: camp_name, F_HYPO: HYPOTHESIS_VALUE,
                                               F_MEDIUM: MEDIUM_EMAIL, F_SOURCE: SOURCE_EMAIL})}
        title = f"{cid} - {camp_name} - {name}"
        has_reply = r.get("has_reply", False)
        label_ids = [L_COLD, L_CONNECTED, L_RESPONDED] if has_reply else [L_COLD]
        lead_body = omit({"title": title, "owner_id": MELISA, "channel": CHANNEL,
                          "label_ids": label_ids, F_LEADCAMP: camp_name, F_OPP: OPP_VALUE})

        row_result = {"email": email, "campaign": camp_name, "campaign_id": cid,
                      "action": "would_create", "has_reply": has_reply,
                      "person_body": person_body, "lead_body": lead_body}

        if has_reply:
            # pull the actual reply text fresh from leads-statistics for this specific email
            reply_hist = None
            skip = 0
            while reply_hist is None:
                page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
                data = page.get("data") or []
                for row in data:
                    if row.get("to") == email:
                        replies = [h for h in (row.get("history") or []) if h.get("type") == "REPLY"]
                        if replies:
                            reply_hist = replies
                        break
                if reply_hist is not None or not page.get("hasMore"):
                    break
                skip += 100
            replies = reply_hist or []
            last_reply = replies[-1] if replies else {}
            activity_body = omit({
                "subject": "Email reply — " + camp_name, "type": "email", "done": True,
                "owner_id": MELISA,
                "note": (("Subject: " + str(last_reply.get("subject")) + "\n\n") if last_reply.get("subject") else "")
                        + str(last_reply.get("email_body") or "")[:8000],
                "due_date": str(last_reply.get("time") or "")[:10],
            })
            row_result["reply_activity_body"] = activity_body
            row_result["reply_count"] = len(replies)
            row_result["forward_note"] = ("FORWARD EMAIL NOT INCLUDED - real external send via "
                                          "Smartlead /forward-email, needs its own separate explicit go")

        to_create.append(row_result)
        results.append(row_result)

    print(f"\n=== DRY-RUN SUMMARY ===")
    print(f"total candidates: {len(rows)}")
    print(f"already exists now (drift since last check): {excluded_now_exists}")
    print(f"excluded, unsubscribed: {excluded_unsub}")
    print(f"excluded, DNC category: {excluded_dnc_cat}")
    print(f"would create: {len(to_create)}")
    with_reply = [x for x in to_create if x.get("has_reply")]
    print(f"  HAS REPLY (priority, full treatment): {len(with_reply)}")
    print(f"  no reply (standard cold backfill): {len(to_create) - len(with_reply)}")

    print(f"\n=== the {len(with_reply)} reply rows, in full ===")
    for r in with_reply:
        print(f"  {r['email']} | {r['campaign'][:40]} | replies={r.get('reply_count')}")
        print(f"    lead labels: {r['lead_body'].get('label_ids')}")
        print(f"    activity note (first 150 chars): {r.get('reply_activity_body',{}).get('note','')[:150]!r}")

    with open(os.path.join(DISC, "london_backfill_dryrun_output.json"), "w", encoding="utf-8") as f:
        json.dump({"total": len(rows), "already_exists_now": excluded_now_exists,
                    "excluded_unsub": excluded_unsub, "excluded_dnc_cat": excluded_dnc_cat,
                    "would_create": len(to_create), "with_reply_count": len(with_reply),
                    "rows": results}, f, indent=2, ensure_ascii=False)
    print(f"\nwrote london_backfill_dryrun_output.json")
    print("\nNO WRITES PERFORMED. Forward-email NOT computed for live use - needs separate explicit go.")


if __name__ == "__main__":
    main()
