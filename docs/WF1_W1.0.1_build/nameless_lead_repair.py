# -*- coding: utf-8 -*-
"""§9f.2 artifact for the 72 nameless Finovate leads (+ the 1 sent-without-lead).

READ-ONLY by default. Writes nothing unless --fire is passed AND --i-have-niks-word is passed.

The defect: WF-2 `Body Lead Create` builds
    title = [campaign_id, campaign_name, lead.full_name].filter(Boolean).join(' - ')
so a null full_name silently degrades the title to "{id} - {campaign}". Between
2026-08-28 11:30:05Z and 12:32:45Z, `Apply Enrich` did not map provider names, so full_name was
null on every WF-2S-replayed SENT (those envelopes carry to_name:null and no lead_data, because
/leads-statistics has no name field at all). The name mapping landed in WF-2 at ~12:32:50Z; the
next three leads created - 12:32:55, 12:33:05, 12:33:15 - are named. No nameless lead has been
created since. So this repairs history only; there is no live leak to close.

Names come from PROVIDER TRUTH (Smartlead /leads?email=), never derived from the address - the
215-name repair rule. A person whose Pipedrive name is still an email address is flagged and, on
fire, repaired from the provider too.
"""
import os, sys, json, ssl, time, urllib.request, urllib.parse

FIRE = "--fire" in sys.argv and "--i-have-niks-word" in sys.argv
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nameless_lead_repair_artifact.json")
CA = os.environ["REQUESTS_CA_BUNDLE"]
PD = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
ctx = ssl.create_default_context(cafile=CA)

CAMPS = {3868449: "[Events Visiting] [FinovateFall 2026] - Noah - Valids",
         3868450: "[Events Visiting] [FinovateFall 2026] - Noah - Catch-alls"}


def _req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Accept": "application/json", "User-Agent": "curl/8.0"}
    if data:
        hdr["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=hdr, method=method)
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(r, context=ctx, timeout=120))
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 429 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            return {"__err": str(e)}
    return {"__err": "retries exhausted"}


def pd(path, method="GET", body=None):
    return _req("https://api.pipedrive.com" + path + ("&" if "?" in path else "?")
                + "api_token=" + PD, method, body)


def sl(path):
    return _req("https://server.smartlead.ai/api/v1" + path
                + ("&" if "?" in path else "?") + "api_key=" + SL)


def looks_like_email(s):
    return "@" in str(s or "")


def choose_name(prov_first, prov_last, pd_name):
    """Which name may go into a title, and from where.

    Order of trust, and the refusal, are the whole point of this function:
      1. Smartlead provider first/last  - provider truth
      2. the Pipedrive person's name    - only if it is a real name
      3. REFUSE                         - never derive a name from an email address
                                          (the 215-name repair rule, 2026-08-18)
    Returns (name, source) or (None, reason).
    """
    provider_name = " ".join([x for x in (prov_first, prov_last) if x]).strip() or None
    if provider_name:
        return provider_name, "smartlead_provider"
    if pd_name and not looks_like_email(pd_name):
        return pd_name, "pipedrive_person"
    return None, ("no provider name and the Pipedrive person is still named by its email "
                  "address - a title must never be derived from an address (215-name rule)")


# ---------------------------------------------------------------- 1. the population
rows = []
for cid, nm in CAMPS.items():
    d = pd("/api/v2/leads/search?" + urllib.parse.urlencode(
        {"term": nm, "fields": "title", "limit": 100}))
    items = ((d.get("data") or {}).get("items") or [])
    if len(items) >= 100:
        raise SystemExit("search saturated for %s - widen before trusting the set" % cid)
    for it in items:
        L = it["item"]
        if str(L.get("title", "")).strip() == "%s - %s" % (cid, nm):
            rows.append({"campaign_id": cid, "campaign_name": nm, "lead_id": L["id"],
                         "current_title": L["title"],
                         "person_id": (L.get("person") or {}).get("id"),
                         "person_name_now": (L.get("person") or {}).get("name")})

print("nameless leads found: %d" % len(rows))

# ---------------------------------------------------------------- 2. provider truth per row
plan, blocked = [], []
for r in rows:
    if not r["person_id"]:
        blocked.append(dict(r, reason="no person on the lead - out of scope for a title rewrite"))
        continue
    p = pd("/api/v2/persons/%s" % r["person_id"]).get("data") or {}
    emails = [e.get("value") for e in (p.get("emails") or []) if e.get("value")]
    email = (emails[0] if emails else None)
    r["person_email"] = email
    r["person_name_pd"] = p.get("name")

    prov_first = prov_last = None
    if email:
        s = sl("/leads?email=" + urllib.parse.quote(email))
        lead = s if isinstance(s, dict) and s.get("email") else None
        if lead:
            prov_first = lead.get("first_name") or None
            prov_last = lead.get("last_name") or None
    r["provider_first"], r["provider_last"] = prov_first, prov_last
    provider_name = " ".join([x for x in (prov_first, prov_last) if x]).strip() or None

    name, src = choose_name(prov_first, prov_last, p.get("name"))
    if not name:
        blocked.append(dict(r, reason=src))
        continue

    r["name_source"] = src
    r["new_title"] = "%s - %s - %s" % (r["campaign_id"], r["campaign_name"], name)
    # a person still carrying an email as its name is a second, separate defect on the same record
    r["person_needs_rename"] = bool(looks_like_email(p.get("name")) and provider_name)
    r["person_new_name"] = provider_name if r["person_needs_rename"] else None
    plan.append(r)

# ---------------------------------------------------------------- 3. the sent-without-lead
missing = {
    "campaign_id": 3868449,
    "email": "pii-a2fe030c@example.invalid",
    "person_id": 59327,
    "person_name": "Person-ab3144af",
    "sent_time": "2026-08-28T11:44:55.937Z",
    "existing_lead": "88bee220 (2548814 - [Events Visiting] Money 20/20 2025 - Valids)",
    "why_no_finovate_lead":
        "his SENT produced no WF-2 execution at all (7 of 48 sends in this campaign did not), and "
        "the 08-28 Finovate backfill then skipped him because its guard was 'person has no lead' "
        "rather than 'person has no lead FOR THIS CAMPAIGN' - he already held a Money 20/20 2025 "
        "lead from 2025-10-16. The other 6 of the 7 had no prior lead and were backfilled.",
    "proposed": "create one campaign lead, exactly as the backfill did for the other 6",
    "included_in_this_fire": False,
}

artifact = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "defect": "WF-2 Body Lead Create title degrades to '{id} - {campaign}' when lead.full_name is null",
    "window": "2026-08-28T11:30:05.618Z .. 2026-08-28T12:32:45.594Z",
    "already_fixed_in_wf2": True,
    "fix_landed_at": "~2026-08-28T12:32:50Z (next 3 leads at 12:32:55/12:33:05/12:33:15 are named)",
    "nameless_created_since_fix": 0,
    "counts": {"found": len(rows), "repairable": len(plan), "blocked": len(blocked),
               "persons_also_needing_rename": sum(1 for r in plan if r["person_needs_rename"])},
    "writes_if_fired": {"lead_title_patches": len(plan),
                        "person_renames": sum(1 for r in plan if r["person_needs_rename"])},
    "reversible": "yes - every current_title is recorded below; replaying them restores the prior state",
    "plan": plan, "blocked": blocked, "sent_without_lead": missing,
}
json.dump(artifact, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("artifact -> %s" % OUT)
print(json.dumps(artifact["counts"], ensure_ascii=False))
for r in plan[:5]:
    print("  %s\n     -> %s   [%s]" % (r["current_title"], r["new_title"], r["name_source"]))
for b in blocked[:5]:
    print("  BLOCKED %s :: %s" % (b["lead_id"][:8], b["reason"]))

if not FIRE:
    print("\nDRY RUN - nothing written. Fire with:  --fire --i-have-niks-word")
    sys.exit(0)

# ---------------------------------------------------------------- 4. fire
ok = err = 0
for r in plan:
    res = pd("/v1/leads/%s" % r["lead_id"], "PATCH", {"title": r["new_title"]})
    if res.get("success") is True:
        ok += 1
    else:
        err += 1
        print("  FAIL lead %s :: %s" % (r["lead_id"], json.dumps(res)[:200]))
    if r["person_needs_rename"]:
        pr = pd("/api/v2/persons/%s" % r["person_id"], "PATCH", {"name": r["person_new_name"]})
        if pr.get("success") is not True:
            print("  FAIL person %s :: %s" % (r["person_id"], json.dumps(pr)[:200]))
print("titles patched: %d ok, %d failed" % (ok, err))

# independent re-scan: prove the CLASS is empty, not that our rows went through
left = 0
for cid, nm in CAMPS.items():
    d = pd("/api/v2/leads/search?" + urllib.parse.urlencode(
        {"term": nm, "fields": "title", "limit": 100}))
    for it in ((d.get("data") or {}).get("items") or []):
        if str(it["item"].get("title", "")).strip() == "%s - %s" % (cid, nm):
            left += 1
print("independent re-scan - nameless leads remaining: %d" % left)
