# -*- coding: utf-8 -*-
"""READ-ONLY. Splits the 'owned by hers but not captured by our creator predicate' population into
   (a) ROSTER GAP        - creator IS a roster human, just one of the four missing from our list
   (b) TRUE OWNER DELTA  - creator is nobody on any roster; only an owner-based rule reaches these
and measures the webform/Memurai exposure a PURE owner rule would re-open.
"""
import json, sys, collections, os

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
a = json.load(open(os.path.join(HERE, "s3_roster_measure.json"), encoding="utf-8"))
leads = json.load(open(os.path.join(HERE, "leads.json"), encoding="utf-8"))
persons = json.load(open(os.path.join(HERE, "persons.json"), encoding="utf-8"))
reg = json.load(open(os.path.join(HERE, "registry_active.json"), encoding="utf-8"))["rows"]

HERS = {int(k): v for k, v in a["roster_hers"].items()}
OURS = {int(k): v for k, v in a["roster_ours"].items()}
GAP = {k: v for k, v in HERS.items() if k not in OURS}
WEBFORM_LEGACY, AUTOMATION = 13015123, 25112064


def slug(u):
    s = str(u or "")
    i = s.lower().find("linkedin.com/in/")
    return (s[i + 16:].split("/")[0].split("?")[0].strip().lower() or None) if i >= 0 else None


rp = {str(r["pipedrive_person_id"]) for r in reg if r.get("pipedrive_person_id") not in (None, "")}
re_ = {str(r["email_lc"]).strip().lower() for r in reg if r.get("email_lc")}
rs = {s for s in (slug(r.get("linkedin_url_norm")) for r in reg) if s}
pidx = {}
for p in persons:
    ems = [str(x.get("value") or "").strip().lower() for x in (p.get("emails") or []) if x.get("value")]
    sl = set()
    for tok in json.dumps(p, ensure_ascii=False).split('"'):
        s = slug(tok)
        if s:
            sl.add(s)
    pidx[p["id"]] = (ems, sl)


def prot(pid):
    if pid is None:
        return False
    if str(pid) in rp:
        return True
    v = pidx.get(pid)
    if not v:
        return False
    return any(e in re_ for e in v[0]) or any(s in rs for s in v[1])


cap_ours = {l["id"] for l in leads
            if (l.get("creator_id") in OURS) or str(l.get("channel_id") or "") == "Surfe"}
newly = [l for l in leads if l.get("owner_id") in HERS
         and l["id"] not in cap_ours and not prot(l.get("person_id"))]
roster_gap = [l for l in newly if l.get("creator_id") in GAP]
true_delta = [l for l in newly if l.get("creator_id") not in GAP]


def desc(l):
    return "creator %s / origin %s / channel %s" % (l.get("creator_id"), l.get("origin"),
                                                    l.get("channel_id"))


print("unprotected leads owned by her nine and NOT captured by our creator predicate: %d" % len(newly))
print("\n(a) ROSTER GAP - creator is a roster human missing from OUR list: %d" % len(roster_gap))
print("    by creator:", json.dumps(
    dict(collections.Counter(GAP[l["creator_id"]] for l in roster_gap).most_common()),
    ensure_ascii=False))
print("\n(b) TRUE OWNER-PREDICATE DELTA - creator on no roster at all: %d" % len(true_delta))
print("    by creator/origin/channel:", json.dumps(
    dict(collections.Counter(desc(l) for l in true_delta).most_common(12)), ensure_ascii=False))

# what a PURE owner rule would re-open
web = [l for l in leads if l.get("owner_id") in HERS
       and (str(l.get("origin") or "").lower() == "webforms" or l.get("creator_id") == WEBFORM_LEGACY)]
mem = [l for l in leads if l.get("owner_id") in HERS
       and ("memurai" in str(l.get("title") or "").lower()
            or "memurai" in str(l.get("channel_id") or "").lower())]
web_unprot = [l for l in web if not prot(l.get("person_id"))]
print("\nLEAK EXPOSURE under a PURE owner rule (no exclusions):")
print("  webform / legacy-Make leads owned by the nine : %d  (unprotected today: %d)"
      % (len(web), len(web_unprot)))
print("  Memurai leads owned by the nine               : %d" % len(mem))

# variant counts
def count(pred):
    return sum(1 for l in leads if pred(l))


def excl(l):
    origin = str(l.get("origin") or "").lower()
    t = str(l.get("title") or "").lower()
    ch = str(l.get("channel_id") or "").lower()
    if l.get("creator_id") == AUTOMATION and origin == "api":
        return True
    if l.get("creator_id") == WEBFORM_LEGACY or origin == "webforms":
        return True
    if "memurai" in t or "memurai" in ch:
        return True
    return False


V = {
 "V0 today  creator in OURS or Surfe, minus exclusions":
    lambda l: ((l.get("creator_id") in OURS) or str(l.get("channel_id") or "") == "Surfe") and not excl(l),
 "V1 her literal rule  owner in HERS, NO exclusions":
    lambda l: l.get("owner_id") in HERS,
 "V2 owner OR creator in HERS+OURS or Surfe, KEEP exclusions":
    lambda l: ((l.get("owner_id") in HERS) or (l.get("owner_id") in OURS)
               or (l.get("creator_id") in HERS) or (l.get("creator_id") in OURS)
               or str(l.get("channel_id") or "") == "Surfe") and not excl(l),
 "V3 owner in HERS+OURS, KEEP exclusions":
    lambda l: ((l.get("owner_id") in HERS) or (l.get("owner_id") in OURS)) and not excl(l),
}
print("\nVARIANT COUNTS over %d live leads:" % len(leads))
for k, f in V.items():
    tot = count(f)
    unp = sum(1 for l in leads if f(l) and not prot(l.get("person_id")))
    wrong = sum(1 for l in leads if f(l) and excl(l))
    print("  %-58s captures %6d | of those unprotected today %6d | excluded-class wrongly caught %4d"
          % (k, tot, unp, wrong))

json.dump({"newly_unprotected": len(newly), "roster_gap": len(roster_gap),
           "roster_gap_by_creator": dict(collections.Counter(
               GAP[l["creator_id"]] for l in roster_gap).most_common()),
           "true_owner_delta": len(true_delta),
           "true_owner_delta_by_creator": dict(collections.Counter(
               desc(l) for l in true_delta).most_common()),
           "webform_owned_by_nine": len(web), "webform_owned_by_nine_unprotected": len(web_unprot),
           "memurai_owned_by_nine": len(mem),
           "variants": {k: {"captures": count(f),
                            "unprotected_today": sum(1 for l in leads if f(l) and not prot(l.get("person_id"))),
                            "excluded_class_caught": sum(1 for l in leads if f(l) and excl(l))}
                        for k, f in V.items()}},
          open(os.path.join(HERE, "refined_split.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nartifact -> AUDIT_S3_ROSTER/refined_split.json")
