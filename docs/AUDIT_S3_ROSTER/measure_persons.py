# -*- coding: utf-8 -*-
"""READ-ONLY person-level measurement for Melisa's final S3 wording. No writes of any kind.

Unit is the PERSON, per her note: "in many cases they don't create leads, they create a person and
then a deal." So deals are walked too, and a person's arrival is derived from the records hanging
off it (leads first, then deals) because a PERSON CARRIES NO CREATOR FIELD in either API version -
only owner_id/owner_name. Persons with neither a lead nor a deal are reported as arrival_unknown,
never bucketed by guess.

Hard limit, measured not assumed: archived leads CANNOT be enumerated. `archived_status` is
accepted by /v1/leads and completely ignored - 3,000 rows requested as `archived` came back with
zero archived, while the control lead 8694ea30 is confirmed archived on a direct GET. Only the
term-based search routes reach archived leads and no term means "all". The label half of the audit
is therefore complete for LIVE leads and bounded for archived ones; the bounded part is run only
for the roster-owned person set, where per-person search is affordable.
"""
import os, json, ssl, sys, time, urllib.request, urllib.parse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ctx = ssl.create_default_context(cafile=os.environ["REQUESTS_CA_BUNDLE"])
PDT = os.environ["PIPEDRIVE_API_TOKEN"]

EIGHT = {17703023: "Toby", 16029123: "Mario Stalder", 24721201: "Jim Ash",
         25733113: "Noah Keimach", 25151686: "Rune Jensen", 25947503: "Matt Carothers",
         24994054: "Chrissy Winkler", 23094002: "Person-f55206df (DEACTIVATED)"}
SERGEY = 21037002
CREATORS_ONLY = {16340280: "Melisa Bahonjic", 25035678: "Slava Kraievskyi"}
AUTOMATION = 25112064
WEBFORM_LEGACY = 13015123
RESP = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
DNCL = "52a7c290-fc73-11f0-ad98-81d4703453f3"
DISQ = "98008920-e942-11ef-b360-57187fe024ea"


def pd(path):
    u = "https://api.pipedrive.com" + path + ("&" if "?" in path else "?") + "api_token=" + PDT
    for a in range(5):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers={"Accept": "application/json"}),
                context=ctx, timeout=180))
        except Exception as e:
            if getattr(e, "code", None) in (429, 502, 503) and a < 4:
                time.sleep(2 ** a); continue
            return {"__err": str(e)}
    return {"__err": "retries"}


def cached(name, fn, minrows=1):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        v = json.load(open(p, encoding="utf-8"))
    else:
        v = fn()
        json.dump(v, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    # a walk that returns nothing is a FAILED READ, never "none exist"
    assert len(v) >= minrows, "%s has %d rows - refusing to measure off that" % (name, len(v))
    print("   %s: %d rows" % (name, len(v)), flush=True)
    return v


def walk_cursor(path, label):
    rows, cur, pages = [], None, 0
    while pages < 900:
        q = {"limit": 500}
        if cur:
            q["cursor"] = cur
        d = pd(path + "?" + urllib.parse.urlencode(q))
        got = d.get("data") or []
        if not got:
            break
        rows += got
        pages += 1
        cur = (d.get("additional_data") or {}).get("next_cursor")
        if pages % 50 == 0:
            print("   %s: %d pages / %d rows" % (label, pages, len(rows)), flush=True)
        if not cur:
            break
    return rows


print("loading caches / walking...", flush=True)
leads = cached("leads.json", lambda: [], 1000)
persons = cached("persons.json", lambda: [], 1000)
deals = cached("deals.json", lambda: walk_cursor("/api/v2/deals", "deals"), 1)
acts = cached("activities.json", lambda: walk_cursor("/api/v2/activities", "activities"), 1)
REG = json.load(open(os.path.join(HERE, "registry_active.json"), encoding="utf-8"))
reg = REG["rows"]
print("   registry active: %d" % len(reg), flush=True)


def slug(u):
    s = str(u or "")
    i = s.lower().find("linkedin.com/in/")
    return (s[i + 16:].split("/")[0].split("?")[0].strip().lower() or None) if i >= 0 else None


reg_pid = {str(r["pipedrive_person_id"]) for r in reg if r.get("pipedrive_person_id") not in (None, "")}
reg_em = {str(r["email_lc"]).strip().lower() for r in reg if r.get("email_lc")}
reg_sl = {s for s in (slug(r.get("linkedin_url_norm")) for r in reg) if s}

pidx = {}
for p in persons:
    o = p.get("owner_id")
    o = o.get("id") if isinstance(o, dict) else o
    ems = [str(x.get("value") or "").strip().lower() for x in (p.get("emails") or []) if x.get("value")]
    sl = set()
    for tok in json.dumps(p, ensure_ascii=False).split('"'):
        s = slug(tok)
        if s:
            sl.add(s)
    pidx[p["id"]] = {"owner": o, "emails": ems, "slugs": sl, "name": p.get("name"),
                     "labels": p.get("label_ids") or []}


def protected(pid):
    if pid is None:
        return False
    if str(pid) in reg_pid:
        return True
    v = pidx.get(pid)
    if not v:
        return False
    return any(e in reg_em for e in v["emails"]) or any(s in reg_sl for s in v["slugs"])


# person -> its leads / deals / reply evidence
by_person_leads = collections.defaultdict(list)
for l in leads:
    if l.get("person_id") is not None:
        by_person_leads[l["person_id"]].append(l)
by_person_deals = collections.defaultdict(list)
for d in deals:
    pidv = d.get("person_id")
    if isinstance(pidv, dict):
        pidv = pidv.get("id")
    if pidv is not None:
        by_person_deals[pidv].append(d)

REPLY_WORDS = ("repl", "responded", "answer")
reply_persons = set()
lead_person = {l["id"]: l.get("person_id") for l in leads}
for a in acts:
    subj = (str(a.get("subject") or "") + " " + str(a.get("note") or "")[:300]).lower()
    if not any(w in subj for w in REPLY_WORDS):
        continue
    pidv = a.get("person_id")
    if isinstance(pidv, dict):
        pidv = pidv.get("id")
    if pidv:
        reply_persons.add(pidv)
    lid = a.get("lead_id")
    if lid and lead_person.get(lid):
        reply_persons.add(lead_person[lid])
print("   persons with a reply-shaped activity: %d" % len(reply_persons), flush=True)


def has_label(pid, label):
    return any(label in (l.get("label_ids") or []) for l in by_person_leads.get(pid, []))


def replied(pid):
    """reply evidence = a reply-shaped activity OR a lead carrying '3. Responded'"""
    return pid in reply_persons or has_label(pid, RESP)


def arrival(pid):
    """derived from the records hanging off the person; persons carry no creator field"""
    ls = by_person_leads.get(pid, [])
    ds = by_person_deals.get(pid, [])
    if not ls and not ds:
        return "arrival_unknown_no_lead_or_deal"
    cands = []
    for l in ls:
        cands.append((l.get("creator_id"), str(l.get("origin") or "").lower(),
                      str(l.get("channel_id") or "")))
    for d in ds:
        c = d.get("creator_user_id")
        c = c.get("id") if isinstance(c, dict) else c
        cands.append((c, "deal", ""))
    for c, origin, ch in cands:
        if c in EIGHT or c == SERGEY:
            return "roster_human"
    for c, origin, ch in cands:
        if ch == "Surfe":
            return "surfe"
    for c, origin, ch in cands:
        if c in CREATORS_ONLY:
            return "melisa_or_slava"
    for c, origin, ch in cands:
        if c == WEBFORM_LEGACY or origin == "webforms":
            return "webform_or_legacy_make"
    for c, origin, ch in cands:
        if c == AUTOMATION:
            return "api_automation"
    return "other_creator"


# ---------------------------------------------------------------- 2. person-level gap, the 8
res8 = {}
for uid, nm in EIGHT.items():
    owned = [pid for pid, v in pidx.items() if v["owner"] == uid]
    gap = [pid for pid in owned if not protected(pid)]
    res8[nm] = {"persons_owned": len(owned), "unprotected": len(gap),
                "by_arrival": dict(collections.Counter(arrival(p) for p in gap).most_common()),
                "with_reply_evidence": sum(1 for p in gap if replied(p))}
tot8_owned = sum(v["persons_owned"] for v in res8.values())
tot8_gap = sum(v["unprotected"] for v in res8.values())

# ---------------------------------------------------------------- 3. Sergey
s_owned = [pid for pid, v in pidx.items() if v["owner"] == SERGEY]
s_gap = [pid for pid in s_owned if not protected(pid)]
s_repl = [pid for pid in s_owned if replied(pid)]
s_repl_gap = [pid for pid in s_gap if replied(pid)]
sergey = {"persons_owned": len(s_owned), "unprotected": len(s_gap),
          "with_reply_evidence": len(s_repl),
          "unprotected_AND_replied": len(s_repl_gap),
          "by_arrival_of_unprotected": dict(collections.Counter(arrival(p) for p in s_gap).most_common())}

# ---------------------------------------------------------------- 4. label side (LIVE leads)
label_side = {}
for nm, lid in (("3. Responded", RESP), ("DO NOT CONTACT", DNCL), ("Disqualified", DISQ)):
    ls = [l for l in leads if lid in (l.get("label_ids") or [])]
    gap = [l for l in ls if not protected(l.get("person_id"))]
    label_side[nm] = {"live_leads": len(ls), "unprotected": len(gap),
                      "by_owner": dict(collections.Counter(
                          (EIGHT.get(l.get("owner_id")) or CREATORS_ONLY.get(l.get("owner_id"))
                           or ("Sergey Cujba" if l.get("owner_id") == SERGEY else str(l.get("owner_id"))))
                          for l in gap).most_common(10))}

# ---------------------------------------------------------------- 6. variant table (PERSON level)
allp = list(pidx.keys())


def cap_creator_roster(pid):
    ls = by_person_leads.get(pid, [])
    ds = by_person_deals.get(pid, [])
    ok = set(EIGHT) | set(CREATORS_ONLY) | {SERGEY}
    for l in ls:
        if l.get("creator_id") in ok or str(l.get("channel_id") or "") == "Surfe":
            return True
    for d in ds:
        c = d.get("creator_user_id")
        c = c.get("id") if isinstance(c, dict) else c
        if c in ok:
            return True
    return False


def leaky_person(pid):
    return arrival(pid) == "webform_or_legacy_make"


VAR = {
 "W0 TODAY  creator-only roster of 8 deployed ids (+Surfe)":
    lambda pid: cap_creator_roster(pid),
 "W1 HER WORDING  owner in the 8  OR (owner=Sergey AND replied)":
    lambda pid: (pidx[pid]["owner"] in EIGHT) or (pidx[pid]["owner"] == SERGEY and replied(pid)),
 "W2 RECONCILED  creator in {8+Melisa+Slava+Sergey}/Surfe  OR owner in 8  OR (Sergey AND replied)":
    lambda pid: cap_creator_roster(pid) or (pidx[pid]["owner"] in EIGHT) \
                or (pidx[pid]["owner"] == SERGEY and replied(pid)),
 "W3 W2 minus webform/legacy-Make arrivals (leak guard ON)":
    lambda pid: (cap_creator_roster(pid) or (pidx[pid]["owner"] in EIGHT)
                 or (pidx[pid]["owner"] == SERGEY and replied(pid))) and not leaky_person(pid),
 "W4 SERGEY WITHOUT the carve-out (owner in 8+Sergey, leak guard ON)":
    lambda pid: ((pidx[pid]["owner"] in EIGHT) or (pidx[pid]["owner"] == SERGEY)) and not leaky_person(pid),
}
variants = {}
for k, f in VAR.items():
    cap = [pid for pid in allp if f(pid)]
    variants[k] = {"persons_captured": len(cap),
                   "new_registry_rows": sum(1 for pid in cap if not protected(pid)),
                   "webform_legacy_wrongly_caught": sum(1 for pid in cap if leaky_person(pid))}

art = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "read_only": True,
       "walks": {"leads": len(leads), "persons": len(persons), "deals": len(deals),
                 "activities": len(acts), "registry_active": len(reg)},
       "archived_limitation": "archived_status is accepted by /v1/leads and IGNORED (3,000 rows "
                              "requested as archived returned 0 archived; control lead 8694ea30 "
                              "is archived on a direct GET). Archived leads cannot be enumerated.",
       "person_has_no_creator_field": True,
       "roster": {"eight_real_sales": EIGHT, "sergey": SERGEY, "creators_only": CREATORS_ONLY},
       "the_eight": res8, "the_eight_totals": {"persons_owned": tot8_owned, "unprotected": tot8_gap},
       "sergey": sergey, "label_side_live_only": label_side, "variants": variants}
json.dump(art, open(os.path.join(HERE, "person_level_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("\n===== THE EIGHT (person level) =====")
for nm, v in sorted(res8.items(), key=lambda x: -x[1]["persons_owned"]):
    print("  %-26s owned %5d  unprotected %5d  replied %4d  %s"
          % (nm, v["persons_owned"], v["unprotected"], v["with_reply_evidence"],
             json.dumps(v["by_arrival"], ensure_ascii=False)[:110]))
print("  TOTAL owned %d | unprotected %d" % (tot8_owned, tot8_gap))
print("\n===== SERGEY =====")
print("  " + json.dumps(sergey, ensure_ascii=False, indent=1)[:700])
print("\n===== LABEL SIDE (live leads only) =====")
for nm, v in label_side.items():
    print("  %-16s live %5d  unprotected %5d  %s"
          % (nm, v["live_leads"], v["unprotected"], json.dumps(v["by_owner"], ensure_ascii=False)[:130]))
print("\n===== VARIANTS (person level, over %d persons) =====" % len(allp))
print("  %-76s %9s %10s %7s" % ("VARIANT", "captures", "new rows", "leaky"))
for k, v in variants.items():
    print("  %-76s %9d %10d %7d" % (k, v["persons_captured"], v["new_registry_rows"],
                                    v["webform_legacy_wrongly_caught"]))
print("\nartifact -> AUDIT_S3_ROSTER/person_level_audit.json")
