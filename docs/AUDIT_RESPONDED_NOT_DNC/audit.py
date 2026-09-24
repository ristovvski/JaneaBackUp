# -*- coding: utf-8 -*-
"""READ-ONLY audit: leads carrying '3. Responded' that are NOT in the DNC registry.

Definition of "in the DNC list": an ACTIVE row in the ledger. That is exactly what the pre-add
gate blocks on (`all.filter(r => r.status === 'active')`), so it is the definition that decides
whether the person can be added to a campaign again.

Identity waterfall, never name-only:
  1. registry.pipedrive_person_id == lead.person_id
  2. registry.email_lc            == any of the person's emails
  3. registry.linkedin_url_norm   == the person's LinkedIn slug
A lead whose person cannot be resolved at all is reported separately, never guessed.

Known blind spots, stated rather than hidden:
  * /v1/leads is LIVE-ONLY - archived leads are invisible to it and `archived_status` is ignored.
    An archived lead carrying '3. Responded' will not appear here.
  * the registry snapshot is the ACTIVE set only, which is the point (see above), but it means a
    person whose row was removed/expired counts as NOT in DNC - correctly, since the gate would
    let them through.
"""
import os, json, ssl, sys, time, urllib.request, urllib.parse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ctx = ssl.create_default_context(cafile=os.environ["REQUESTS_CA_BUNDLE"])
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
N8K = os.environ["N8N_API_KEY"]
NBASE = os.environ["N8N_BASE_URL"] + "/api/v1"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
DNC_LABEL = "52a7c290-fc73-11f0-ad98-81d4703453f3"
MAX_PAGES = int(os.environ.get("MAX_PAGES", "300"))


def pd(path):
    u = "https://api.pipedrive.com" + path + ("&" if "?" in path else "?") + "api_token=" + PDT
    for a in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(u, headers={"Accept": "application/json"}),
                context=ctx, timeout=120))
        except Exception as e:
            if getattr(e, "code", None) == 429 and a < 3:
                time.sleep(2 ** a); continue
            return {"__err": str(e)}
    return {"__err": "retries"}


def n8n(path):
    return urllib.request.urlopen(urllib.request.Request(
        NBASE + path, headers={"X-N8N-API-KEY": N8K}), context=ctx, timeout=300)


def slug(u):
    s = str(u or "")
    i = s.lower().find("linkedin.com/in/")
    if i < 0:
        return None
    return s[i + 16:].split("/")[0].split("?")[0].strip().lower() or None


# ---------------------------------------------------------------- 1. all live leads
print("walking live leads (sort=add_time DESC)...")
leads, start, pages = [], 0, 0
while pages < MAX_PAGES:
    d = pd("/v1/leads?" + urllib.parse.urlencode(
        {"limit": 500, "start": start, "sort": "add_time DESC"}))
    rows = d.get("data") or []
    if not rows:
        break
    leads += rows
    pages += 1
    pg = ((d.get("additional_data") or {}).get("pagination") or {})
    if pages % 10 == 0:
        print("   %d pages, %d leads, oldest %s" % (pages, len(leads), rows[-1].get("add_time")[:10]))
    if not pg.get("more_items_in_collection"):
        break
    start = pg.get("next_start") if pg.get("next_start") is not None else start + len(rows)
truncated = pages >= MAX_PAGES
print("   leads walked: %d over %d pages%s" % (len(leads), pages, "  *** PAGE CAP HIT ***" if truncated else ""))
print("   oldest add_time seen: %s" % (leads[-1].get("add_time") if leads else "n/a"))

resp = [l for l in leads if RESPONDED in (l.get("label_ids") or [])]
print("   carrying '3. Responded': %d" % len(resp))

# ---------------------------------------------------------------- 2. registry active set
print("reading the DNC registry active set...")
e = json.load(n8n("/executions?workflowId=QO1zRhUfG7otk06N&limit=1"))["data"][0]
ex = json.loads(n8n("/executions/%s?includeData=true" % e["id"]).read())
reg = [r["json"] for r in
       ex["data"]["resultData"]["runData"]["Get Registry Active Rows"][0]["data"]["main"][0]]
print("   active registry rows: %d  (detector exec %s, %s)" % (len(reg), e["id"], e["startedAt"][:19]))

by_pid = {}
by_email = {}
by_slug = {}
for r in reg:
    if r.get("pipedrive_person_id") not in (None, ""):
        by_pid.setdefault(str(r["pipedrive_person_id"]), r)
    if r.get("email_lc"):
        by_email.setdefault(str(r["email_lc"]).strip().lower(), r)
    s = slug(r.get("linkedin_url_norm"))
    if s:
        by_slug.setdefault(s, r)
print("   index: %d person ids, %d emails, %d slugs" % (len(by_pid), len(by_email), len(by_slug)))

# ---------------------------------------------------------------- 3. match
hit_pid, need_person = [], []
for l in resp:
    pid = l.get("person_id")
    if pid is not None and str(pid) in by_pid:
        hit_pid.append((l, by_pid[str(pid)]))
    else:
        need_person.append(l)
print("   matched by person_id: %d | needing email/slug check: %d" % (len(hit_pid), len(need_person)))

gap, matched_deep, unresolved = [], [], []
pcache = {}
for i, l in enumerate(need_person, 1):
    pid = l.get("person_id")
    if pid is None:
        unresolved.append({"lead_id": l["id"], "title": l.get("title"),
                           "why": "lead has no person_id at all"})
        continue
    if pid not in pcache:
        pcache[pid] = pd("/api/v2/persons/%s" % pid).get("data")
    p = pcache[pid]
    if not p:
        unresolved.append({"lead_id": l["id"], "title": l.get("title"), "person_id": pid,
                           "why": "person id does not resolve in Pipedrive"})
        continue
    emails = [str(x.get("value") or "").strip().lower() for x in (p.get("emails") or []) if x.get("value")]
    slugs = set()
    for tok in json.dumps(p, ensure_ascii=False).split('"'):
        s = slug(tok)
        if s:
            slugs.add(s)
    r = None
    how = None
    for em in emails:
        if em in by_email:
            r, how = by_email[em], "email"; break
    if r is None:
        for s in slugs:
            if s in by_slug:
                r, how = by_slug[s], "linkedin_slug"; break
    rec = {"lead_id": l["id"], "title": l.get("title"), "add_time": l.get("add_time"),
           "person_id": pid, "person_name": p.get("name"), "emails": emails,
           "slugs": sorted(slugs), "owner_id": l.get("owner_id"),
           "labels": l.get("label_ids") or [],
           "has_dnc_label": DNC_LABEL in (l.get("label_ids") or [])}
    if r is None:
        gap.append(rec)
    else:
        matched_deep.append((rec, how, r.get("id")))
    if i % 100 == 0:
        print("      resolved %d/%d, gap so far %d" % (i, len(need_person), len(gap)))

print("\n================ RESULT ================")
print("leads with '3. Responded' (live only) : %d" % len(resp))
print("  in DNC via person_id                : %d" % len(hit_pid))
print("  in DNC via email/slug               : %d" % len(matched_deep))
print("  NOT IN DNC                          : %d" % len(gap))
print("  unresolvable (listed, not guessed)  : %d" % len(unresolved))

art = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "read_only": True,
       "definition": "in DNC = an ACTIVE ledger row; that is what the pre-add gate blocks on",
       "blind_spots": ["/v1/leads is LIVE-ONLY: an archived lead carrying '3. Responded' cannot appear",
                       "registry snapshot is the ACTIVE set; removed/expired rows count as not-in-DNC, "
                       "which is correct because the gate would let them through"],
       "leads_walked": len(leads), "pages": pages, "page_cap_hit": truncated,
       "oldest_lead_add_time": leads[-1].get("add_time") if leads else None,
       "registry_active_rows": len(reg), "detector_exec": e["id"],
       "counts": {"responded_live_leads": len(resp), "in_dnc_by_person_id": len(hit_pid),
                  "in_dnc_by_email_or_slug": len(matched_deep), "not_in_dnc": len(gap),
                  "unresolvable": len(unresolved)},
       "not_in_dnc": gap, "unresolvable": unresolved}
os.makedirs(HERE, exist_ok=True)
json.dump(art, open(os.path.join(HERE, "responded_not_dnc.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nartifact -> AUDIT_RESPONDED_NOT_DNC/responded_not_dnc.json")

if gap:
    print("\nby owner:", dict(collections.Counter(g["owner_id"] for g in gap).most_common()))
    print("carrying DO NOT CONTACT label too:", sum(1 for g in gap if g["has_dnc_label"]))
    print("\nfirst 25:")
    for g in gap[:25]:
        print("   p%-7s %-26s %s" % (g["person_id"], str(g["person_name"])[:26],
                                     str(g["title"])[:56]))
