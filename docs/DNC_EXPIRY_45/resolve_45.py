# -*- coding: utf-8 -*-
"""READ-ONLY resolution of the 45 registry rows that are status=active with a past expires_at.

Identity waterfall, in strict order, NEVER name-only:
  1. the stored pipedrive_person_id, and then CORROBORATED against the row's email or LinkedIn
     slug. A stored id that does not corroborate is downgraded, not trusted - a person id can be
     stale, merged away, or simply wrong, and 162 London leads were once bound to the wrong person
     by exactly that kind of optimism.
  2. persons/search by email, exact_match
  3. persons/search by the LinkedIn slug
  4. unresolvable - listed, never guessed

Reply evidence is PROVIDER TRUTH, not the Pipedrive label:
  Smartlead  GET /leads?email=  ->  lead_campaign_data[].last_reply_at
  Pipedrive  activities whose subject looks like a logged reply (our own automations write these)
  HeyReach   NOT CONSULTED - the workspace only holds data from 2026-07-13 onward and every row
             here is a 2025 contact, so absence there would prove nothing. Stated, not silently
             counted as "no reply".
"""
import os, sys, json, csv, ssl, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = sys.argv[1]
OUT = os.path.join(HERE, "resolve_45_artifact.json")
ctx = ssl.create_default_context(cafile=os.environ["REQUESTS_CA_BUNDLE"])
PD = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]

LAB = {"a6d359b0-6a45-11ed-ab46-5b95b19fcb18": "1. Cold",
       "ca698a50-bdfb-11ef-8172-510383583b0e": "2. Connected",
       "c9d4b550-bcf3-11ef-a843-357f91e826ec": "3. Responded",
       "52a7c290-fc73-11f0-ad98-81d4703453f3": "DO NOT CONTACT"}


def _req(url):
    for attempt in range(4):
        try:
            r = urllib.request.Request(url, headers={"Accept": "application/json",
                                                     "User-Agent": "curl/8.0"})
            return json.load(urllib.request.urlopen(r, context=ctx, timeout=90))
        except Exception as e:
            if getattr(e, "code", None) == 429 and attempt < 3:
                time.sleep(2 ** attempt); continue
            return {"__err": str(e)}
    return {"__err": "retries exhausted"}


def pd(path):
    return _req("https://api.pipedrive.com" + path
                + ("&" if "?" in path else "?") + "api_token=" + PD)


def sl(path):
    return _req("https://server.smartlead.ai/api/v1" + path
                + ("&" if "?" in path else "?") + "api_key=" + SL)


def slug_of(url):
    s = str(url or "").rstrip("/").split("/")[-1].strip().lower()
    return s or None


def emails_of(person):
    return [str(e.get("value") or "").strip().lower()
            for e in (person.get("emails") or []) if e.get("value")]


def person_slugs(person):
    """LinkedIn slugs anywhere on the person record - custom fields are a FLAT dict on /api/v2."""
    out = set()
    blob = json.dumps(person, ensure_ascii=False)
    for tok in blob.split('"'):
        if "linkedin.com/in/" in tok:
            s = slug_of(tok)
            if s:
                out.add(s)
    return out


_raw = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
# the export carries a doubled BOM, so even utf-8-sig leaves ﻿ glued to the first header.
# Strip it rather than index by position - a header that silently renames a column is how a
# join goes wrong without anyone noticing.
rows = [{(k or "").replace("﻿", "").strip(): v for k, v in r.items()} for r in _raw]
assert rows and "id" in rows[0], "unexpected header: %r" % (list(_raw[0].keys())[:4],)
print("csv rows: %d" % len(rows))

results = []
for i, r in enumerate(rows, 1):
    email = (r.get("email_lc") or "").strip().lower() or None
    slug = slug_of(r.get("linkedin_url_norm"))
    stored = (r.get("pipedrive_person_id") or "").strip() or None
    rec = {"registry_id": r["id"], "identity_key": r["identity_key"],
           "full_name_in_registry": r.get("full_name"), "email_lc": email,
           "linkedin_slug": slug, "stored_person_id": stored,
           "reason": r.get("reason"), "entry_type": r.get("entry_type"),
           "reply_category": r.get("reply_category") or None,
           "also_flagged": r.get("also_flagged"),
           "expires_at_raw": r.get("expires_at")}

    person, how = None, None
    # --- 1. stored id, then corroborate
    if stored:
        p = pd("/api/v2/persons/%s" % stored).get("data")
        if p:
            pe, ps = emails_of(p), person_slugs(p)
            if email and email in pe:
                person, how = p, "stored_id_corroborated_by_email"
            elif slug and slug in ps:
                person, how = p, "stored_id_corroborated_by_slug"
            else:
                person, how = p, "stored_id_UNCORROBORATED"
    # --- 2. email
    if person is None and email:
        s = pd("/api/v2/persons/search?" + urllib.parse.urlencode(
            {"term": email, "fields": "email", "exact_match": "true", "limit": 10}))
        items = ((s.get("data") or {}).get("items") or [])
        if len(items) == 1:
            person = pd("/api/v2/persons/%s" % items[0]["item"]["id"]).get("data")
            how = "email_exact"
        elif len(items) > 1:
            how = "email_ambiguous_%d" % len(items)
    # --- 3. linkedin slug
    if person is None and slug:
        s = pd("/api/v2/persons/search?" + urllib.parse.urlencode(
            {"term": slug, "limit": 10}))
        items = ((s.get("data") or {}).get("items") or [])
        cand = [it["item"] for it in items
                if slug in person_slugs(pd("/api/v2/persons/%s" % it["item"]["id"]).get("data") or {})]
        if len(cand) == 1:
            person = pd("/api/v2/persons/%s" % cand[0]["id"]).get("data")
            how = "linkedin_slug"
        elif len(cand) > 1:
            how = "slug_ambiguous_%d" % len(cand)

    rec["resolution"] = how or "UNRESOLVED"
    if not person:
        rec["resolved"] = False
        results.append(rec)
        print("  %2d/%d  %-26s UNRESOLVED (%s)" % (i, len(rows), rec["identity_key"][:26], how))
        continue

    rec["resolved"] = True
    rec["person_id"] = person.get("id")
    rec["person_name"] = person.get("name")
    rec["person_emails"] = emails_of(person)
    rec["owner_id"] = (person.get("owner_id") or {}).get("id") \
        if isinstance(person.get("owner_id"), dict) else person.get("owner_id")

    leads = pd("/v1/leads?person_id=%s&limit=50&sort=%s"
               % (person["id"], urllib.parse.quote("add_time DESC"))).get("data") or []
    rec["leads"] = [{"id": l["id"], "title": l.get("title"),
                     "labels": [LAB.get(x, x) for x in (l.get("label_ids") or [])],
                     "archived": l.get("is_archived"), "add_time": l.get("add_time"),
                     "owner_id": l.get("owner_id")} for l in leads]
    rec["has_responded_label"] = any("3. Responded" in l["labels"] for l in rec["leads"])
    rec["has_dnc_label"] = any("DO NOT CONTACT" in l["labels"] for l in rec["leads"])

    deals = pd("/api/v2/deals?person_id=%s&limit=50" % person["id"]).get("data") or []
    rec["deals"] = [{"id": d.get("id"), "title": d.get("title"), "status": d.get("status"),
                     "stage_id": d.get("stage_id"), "value": d.get("value")} for d in deals]
    rec["open_or_won_deal"] = any(d.get("status") in ("open", "won") for d in deals)

    acts = pd("/api/v2/activities?person_id=%s&limit=100" % person["id"]).get("data") or []
    reply_acts = [a for a in acts
                  if "repl" in str(a.get("subject") or "").lower()
                  or "repl" in str(a.get("note") or "").lower()[:400]]
    rec["activity_count"] = len(acts)
    rec["pd_reply_activities"] = [{"add_time": a.get("add_time"),
                                   "subject": (a.get("subject") or "")[:90]}
                                  for a in reply_acts][:5]

    # --- provider truth: Smartlead
    rec["sl_present"] = False
    rec["sl_last_reply_at"] = None
    rec["sl_campaigns"] = []
    if email:
        d = sl("/leads?email=" + urllib.parse.quote(email))
        if isinstance(d, dict) and d.get("email"):
            rec["sl_present"] = True
            for c in (d.get("lead_campaign_data") or []):
                rec["sl_campaigns"].append({"campaign_id": c.get("campaign_id"),
                                            "name": c.get("campaign_name"),
                                            "last_reply_at": c.get("last_reply_at"),
                                            "last_sent_at": c.get("last_sent_at"),
                                            "category_id": c.get("lead_category_id")})
            reps = [c["last_reply_at"] for c in rec["sl_campaigns"] if c["last_reply_at"]]
            rec["sl_last_reply_at"] = sorted(reps)[-1] if reps else None

    # ---------------- classification
    hard = []
    if rec["sl_last_reply_at"]:
        hard.append("smartlead last_reply_at=" + str(rec["sl_last_reply_at"])[:10])
    if rec["pd_reply_activities"]:
        hard.append("%d reply activity(ies) in Pipedrive" % len(rec["pd_reply_activities"]))
    if rec["open_or_won_deal"]:
        hard.append("open/won deal")
    if r.get("reason") == "meeting_dnc":
        hard.append("meeting_dnc (S2 meeting sweep: '5. Meeting' label UNION Qualified Meeting Set)")
    if (rec["reply_category"] or "") in ("meeting_no_conversion", "positive_reply_no_conversion",
                                         "not_interested", "disqualified_generic",
                                         "responded_generic"):
        hard.append("curated reply_category=" + rec["reply_category"])

    soft = []
    if rec["has_responded_label"]:
        soft.append("'3. Responded' label only")

    if hard:
        rec["klass"] = "a_genuine_reply_or_meeting"
        rec["evidence"] = hard
    elif soft:
        rec["klass"] = "a_label_only_no_provider_evidence"
        rec["evidence"] = soft
    else:
        rec["klass"] = "b_contact_only_leftover"
        rec["evidence"] = []
    results.append(rec)
    print("  %2d/%d  %-26s %-28s %s" % (i, len(rows), rec["identity_key"][:26],
                                        rec["resolution"], rec["klass"]))

counts = {}
for x in results:
    counts[x.get("klass", "unresolved")] = counts.get(x.get("klass", "unresolved"), 0) + 1
counts["resolved"] = sum(1 for x in results if x["resolved"])
counts["unresolved"] = sum(1 for x in results if not x["resolved"])
counts["uncorroborated_stored_id"] = sum(
    1 for x in results if x["resolution"] == "stored_id_UNCORROBORATED")
counts["with_open_or_won_deal"] = sum(1 for x in results if x.get("open_or_won_deal"))
counts["with_smartlead_reply"] = sum(1 for x in results if x.get("sl_last_reply_at"))
counts["with_pd_reply_activity"] = sum(1 for x in results if x.get("pd_reply_activities"))
counts["not_in_smartlead_at_all"] = sum(1 for x in results if x["resolved"] and not x.get("sl_present"))

json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source_csv": os.path.basename(CSV_IN),
           "heyreach": "not consulted - workspace history starts 2026-07-13, every row here is a "
                       "2025 contact, so absence there would prove nothing",
           "counts": counts, "rows": results},
          open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\ncounts: " + json.dumps(counts, ensure_ascii=False))
print("artifact -> %s" % OUT)
