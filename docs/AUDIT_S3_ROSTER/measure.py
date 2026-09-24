# -*- coding: utf-8 -*-
"""READ-ONLY measurement for the S3 owner-vs-creator predicate question.

Two bulk walks (leads, persons) instead of per-record fetches, then everything is computed
locally. No writes of any kind.

The question: our watcher captures on CREATOR (roster) or channel_id === 'Surfe'. Melisa's rule is
OWNED BY one of nine. So a lead created by Surfe or by an automation but OWNED by Mario is
protected under her rule and not under ours. This measures exactly that population and splits it
by creator, so the cost of an owner-based predicate is visible before anyone changes it.
"""
import os, json, ssl, sys, time, urllib.request, urllib.parse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ctx = ssl.create_default_context(cafile=os.environ["REQUESTS_CA_BUNDLE"])
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
N8K = os.environ["N8N_API_KEY"]
NBASE = os.environ["N8N_BASE_URL"] + "/api/v1"

# Melisa's nine, resolved against the real user list
HERS = {17703023: "Toby", 16029123: "Mario Stalder", 21037002: "Sergey Cujba",
        24721201: "Jim Ash", 25733113: "Noah Keimach", 25151686: "Rune Jensen",
        25947503: "Matt Carothers", 24994054: "Chrissy Winkler",
        23094002: "Person-f55206df (DEACTIVATED)"}
# what the S3 watcher actually has deployed
OURS = {17703023: "Toby", 24721201: "Jim Ash", 16029123: "Mario Stalder",
        25733113: "Noah Keimach", 24902545: "Araks Grigoryan", 25151686: "Rune Jensen",
        25035678: "Slava Kraievskyi", 16340280: "Melisa Bahonjic"}
AUTOMATION = 25112064       # Mykyta / API token
WEBFORM_LEGACY = 13015123   # Marci Csomor - the legacy Make/webform token


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


def cached(name, fn):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        print("   (cache) %s" % name, flush=True)
        return json.load(open(p, encoding="utf-8"))
    v = fn()
    json.dump(v, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return v


def walk(path, label, extra=None):
    rows, start, pages = [], 0, 0
    while pages < 400:
        q = {"limit": 500, "start": start}
        if extra:
            q.update(extra)
        d = pd(path + "?" + urllib.parse.urlencode(q))
        got = d.get("data") or []
        if not got:
            break
        rows += got
        pages += 1
        pg = ((d.get("additional_data") or {}).get("pagination") or {})
        if pages % 20 == 0:
            print("   %s: %d pages, %d rows" % (label, pages, len(rows)), flush=True)
        if not pg.get("more_items_in_collection"):
            break
        start = pg.get("next_start") if pg.get("next_start") is not None else start + len(got)
    print("   %s: %d rows over %d pages" % (label, len(rows), pages), flush=True)
    return rows


def slug(u):
    s = str(u or "")
    i = s.lower().find("linkedin.com/in/")
    return (s[i + 16:].split("/")[0].split("?")[0].strip().lower() or None) if i >= 0 else None


print("walking leads...", flush=True)
leads = cached("leads.json", lambda: walk("/v1/leads", "leads", {"sort": "add_time DESC"}))
def walk_cursor(path, label):
    """/api/v2/* uses CURSOR pagination. Passing start= there is a hard 400, which on the first
    attempt made this walk return an empty list that was then cached and treated as data - every
    email/slug match silently degraded to person-id-only. Guarded below so it cannot recur."""
    rows, cur, pages = [], None, 0
    while pages < 600:
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
        if pages % 40 == 0:
            print("   %s: %d pages, %d rows" % (label, pages, len(rows)), flush=True)
        if not cur:
            break
    print("   %s: %d rows over %d pages" % (label, len(rows), pages), flush=True)
    return rows


print("walking persons...", flush=True)
persons = cached("persons.json", lambda: walk_cursor("/api/v2/persons", "persons"))
# A walk that returns nothing is a FAILED READ, never "no persons". Fail loudly.
assert len(persons) > 1000, ("persons walk returned %d rows - refusing to measure off that"
                             % len(persons))

print("registry...", flush=True)


def reg_rows():
    def n8n(p):
        return urllib.request.urlopen(urllib.request.Request(
            NBASE + p, headers={"X-N8N-API-KEY": N8K}), context=ctx, timeout=300)
    e = json.load(n8n("/executions?workflowId=QO1zRhUfG7otk06N&limit=1"))["data"][0]
    ex = json.loads(n8n("/executions/%s?includeData=true" % e["id"]).read())
    rows = [r["json"] for r in
            ex["data"]["resultData"]["runData"]["Get Registry Active Rows"][0]["data"]["main"][0]]
    return {"exec": e["id"], "started": e["startedAt"], "rows": rows}


REG = cached("registry_active.json", reg_rows)
reg = REG["rows"]
print("   active registry rows: %d (detector exec %s)" % (len(reg), REG["exec"]), flush=True)

reg_pid = {str(r["pipedrive_person_id"]) for r in reg if r.get("pipedrive_person_id") not in (None, "")}
reg_em = {str(r["email_lc"]).strip().lower() for r in reg if r.get("email_lc")}
reg_sl = {s for s in (slug(r.get("linkedin_url_norm")) for r in reg) if s}
print("   index: %d pids, %d emails, %d slugs" % (len(reg_pid), len(reg_em), len(reg_sl)), flush=True)

# person index: id -> {emails, slugs, owner}
pidx = {}
for p in persons:
    ems = [str(x.get("value") or "").strip().lower()
           for x in (p.get("emails") or []) if x.get("value")]
    sls = set()
    for tok in json.dumps(p, ensure_ascii=False).split('"'):
        s = slug(tok)
        if s:
            sls.add(s)
    own = p.get("owner_id")
    if isinstance(own, dict):
        own = own.get("id")
    pidx[p["id"]] = {"emails": ems, "slugs": sls, "owner_id": own, "name": p.get("name")}
print("   person index: %d" % len(pidx), flush=True)


def protected(person_id):
    """Is this person on the ACTIVE DNC list? person id -> email -> slug, never name."""
    if person_id is None:
        return False, "no_person"
    if str(person_id) in reg_pid:
        return True, "person_id"
    p = pidx.get(person_id)
    if not p:
        return False, "person_not_in_index"
    for e in p["emails"]:
        if e in reg_em:
            return True, "email"
    for s in p["slugs"]:
        if s in reg_sl:
            return True, "slug"
    return False, "absent"


def creator_bucket(l):
    c = l.get("creator_id")
    origin = str(l.get("origin") or "").lower()
    if c in HERS or c in OURS:
        return "roster_human"
    if str(l.get("channel_id") or "") == "Surfe":
        return "surfe"
    if c == AUTOMATION:
        return "api_automation" if origin == "api" else "api_token_other_origin"
    if c == WEBFORM_LEGACY or origin == "webforms":
        return "webform_or_legacy_make"
    return "other_creator_%s" % c


# ---------------------------------------------------------------- the measurement
res = {}
for label, roster in (("hers", HERS), ("ours", OURS)):
    owned = [l for l in leads if l.get("owner_id") in roster]
    gap = [l for l in owned if not protected(l.get("person_id"))[0]]
    res[label] = {
        "leads_owned": len(owned),
        "leads_owned_unprotected": len(gap),
        "by_creator_bucket": dict(collections.Counter(creator_bucket(l) for l in gap).most_common()),
        "by_owner": dict(collections.Counter(roster[l["owner_id"]] for l in gap).most_common()),
    }

# what an OWNER predicate newly captures that CREATOR does not
creator_captured = set()
for l in leads:
    c = l.get("creator_id")
    if (c in OURS) or (str(l.get("channel_id") or "") == "Surfe"):
        creator_captured.add(l["id"])
owner_hers = {l["id"] for l in leads if l.get("owner_id") in HERS}
newly = [l for l in leads if l["id"] in owner_hers and l["id"] not in creator_captured]
newly_unprot = [l for l in newly if not protected(l.get("person_id"))[0]]

# persons owned by the roster with no active row
pers_gap = {}
for label, roster in (("hers", HERS), ("ours", OURS)):
    owned_p = [pid for pid, v in pidx.items() if v["owner_id"] in roster]
    unprot = [pid for pid in owned_p if not protected(pid)[0]]
    pers_gap[label] = {"persons_owned": len(owned_p), "persons_owned_unprotected": len(unprot)}

art = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "read_only": True,
    "leads_walked": len(leads), "persons_walked": len(persons),
    "registry_active_rows": len(reg), "detector_exec": REG["exec"],
    "roster_ours": OURS, "roster_hers": HERS,
    "roster_diff": {
        "in_ours_not_hers": {k: v for k, v in OURS.items() if k not in HERS},
        "in_hers_not_ours": {k: v for k, v in HERS.items() if k not in OURS},
        "in_both": {k: v for k, v in OURS.items() if k in HERS}},
    "leads": res, "persons": pers_gap,
    "owner_predicate_delta": {
        "leads_owned_by_hers_not_captured_by_creator_predicate": len(newly),
        "of_those_unprotected_today": len(newly_unprot),
        "by_creator_bucket": dict(collections.Counter(creator_bucket(l) for l in newly_unprot).most_common()),
        "sample": [{"lead_id": l["id"], "title": str(l.get("title"))[:70],
                    "owner": HERS.get(l.get("owner_id")), "creator_id": l.get("creator_id"),
                    "origin": l.get("origin"), "channel_id": l.get("channel_id"),
                    "add_time": l.get("add_time")} for l in newly_unprot[:30]]},
}
json.dump(art, open(os.path.join(HERE, "s3_roster_measure.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n===== RESULT =====")
print(json.dumps({k: art[k] for k in
                  ("leads_walked", "persons_walked", "registry_active_rows",
                   "roster_diff", "leads", "persons", "owner_predicate_delta")},
                 ensure_ascii=False, indent=1)[:4000])
print("\nartifact -> AUDIT_S3_ROSTER/s3_roster_measure.json")
