"""I-04 daily snapshot — the prerequisite the weekly sweep identified.

WHY THIS EXISTS: archived leads are invisible to every Pipedrive list read (`/v1/leads`,
`?person_id=`, and `archived_status` is silently ignored). So a lead that leaves the estate can only
be detected by comparing today's id set against a set persisted BEFORE it left. A day without a
snapshot is permanent blindness — the 13-14 Aug archival wave could only be bounded, never counted.

READ-ONLY against every system. The only thing written is a gzipped snapshot under
audit-artifacts/snapshots/.

USAGE
  python i04_snapshot.py                      # live walk, snapshot for today (production)
  python i04_snapshot.py --date 2026-08-19 \
      --leads x1_allleads.json --persons v1_walk.json    # seed from an existing walk

Snapshot shape (deliberately minimal - it must stay cheap to keep forever):
  {"date", "captured_at", "source", "counts",
   "leads":   {lead_id: [sorted_label_ids_joined, person_id, add_time]},
   "persons": {person_id: [add_time, update_time, email_lc, lh_slug, dnc686]},
   "dnc_labelled": [lead_id, ...]}
"""
import sys, os, json, io, gzip, re, argparse
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aud

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPDIR = r"C:\Users\User\Desktop\Нова папка\audit-artifacts\snapshots"
DNC_LABEL = "52a7c290-fc73-11f0-ad98-81d4703453f3"
LH_KEY = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
DNC_FIELD = "9c018b7406ebc481b9c108a487f76c4d09f91c9b"   # person field 9180 'DNC Status'
DNC_ACTIVE = "686"                                        # option id 686 = dnc_active
RX = re.compile(r"linkedin\.com/(?:in|pub)/([^/?#\s]+)")


def slug(u):
    m = RX.search(str(u or "").lower())
    return m.group(1) if m else ""


def walk_leads_live():
    L, start, pages = {}, 0, 0
    while pages < 4000:
        pages += 1
        r = aud.pd("/v1/leads", limit=100, start=start)
        for x in (r.get("data") or []):
            L[x["id"]] = {"label_ids": x.get("label_ids") or [], "person_id": x.get("person_id"),
                          "add_time": x.get("add_time")}
        ad = (r.get("additional_data") or {}).get("pagination") or {}
        if not ad.get("more_items_in_collection"):
            break
        start = ad.get("next_start")
    return L, pages


def walk_persons_live():
    P, cur, pages = {}, None, 0
    while pages < 4000:
        pages += 1
        q = {"limit": 100}
        if cur:
            q["cursor"] = cur
        r = aud.pd("/api/v2/persons", **q)
        for p in (r.get("data") or []):
            cf = p.get("custom_fields") or {}
            em = [e.get("value") for e in (p.get("emails") or []) if e.get("value")]
            P[str(p["id"])] = {"add_time": p.get("add_time"), "update_time": p.get("update_time"),
                               "email": (em[0].strip().lower() if em else ""),
                               "lh": cf.get(LH_KEY), "dnc": cf.get(DNC_FIELD)}
        cur = (r.get("additional_data") or {}).get("next_cursor")
        if not cur:
            break
    return P, pages


def from_cache(leads_file, persons_file):
    lj = json.load(io.open(os.path.join(HERE, leads_file), encoding="utf-8"))
    L = {}
    for lid, v in (lj.get("leads") or {}).items():
        L[lid] = {"label_ids": v.get("label_ids") or [], "person_id": v.get("person_id"),
                  "add_time": v.get("add_time")}
    pj = json.load(io.open(os.path.join(HERE, persons_file), encoding="utf-8"))
    P = {}
    # a cached walk that never captured the DNC field must record UNKNOWN, never 0 - a missing
    # measurement masquerading as zero would make the next diff report a fake +2262 jump
    has_dnc = any("dnc" in (v or {}) for v in list((pj.get("persons") or {}).values())[:50])
    for pid, v in (pj.get("persons") or {}).items():
        cf = v.get("cf") or {}
        lh = cf.get("lh") if "lh" in cf else v.get("lh")
        em = v.get("emails") or []
        P[pid] = {"add_time": v.get("add_time"), "update_time": v.get("update_time"),
                  "email": (str(em[0]).strip().lower() if em else ""),
                  "lh": lh, "dnc": (v.get("dnc") if has_dnc else "UNKNOWN")}
    return L, P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--leads")
    ap.add_argument("--persons")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    date = a.date or now.strftime("%Y-%m-%d")

    if a.leads and a.persons:
        L, P = from_cache(a.leads, a.persons)
        src = "cache:%s+%s" % (a.leads, a.persons)
        lp = pp = None
    else:
        L, lp = walk_leads_live()
        P, pp = walk_persons_live()
        src = "live walk"

    snap = {
        "date": date, "captured_at": now.isoformat(), "source": src,
        "counts": {"leads": len(L), "persons": len(P), "lead_pages": lp, "person_pages": pp,
                   "dnc_labelled": sum(1 for v in L.values() if DNC_LABEL in (v["label_ids"] or [])),
                   "dnc_field_686": (None if any(str(v.get("dnc")) == "UNKNOWN" for v in P.values())
                                     else sum(1 for v in P.values() if str(v.get("dnc")) == DNC_ACTIVE))},
        "leads": dict((lid, ["|".join(sorted(v["label_ids"] or [])), v["person_id"], v["add_time"]])
                      for lid, v in L.items()),
        "persons": dict((pid, [v["add_time"], v["update_time"], v["email"], slug(v.get("lh")),
                               (None if str(v.get("dnc")) == "UNKNOWN"
                                else (1 if str(v.get("dnc")) == DNC_ACTIVE else 0))])
                          for pid, v in P.items()),
        "dnc_labelled": sorted(l for l, v in L.items() if DNC_LABEL in (v["label_ids"] or [])),
    }
    if not os.path.isdir(SNAPDIR):
        os.makedirs(SNAPDIR)
    path = os.path.join(SNAPDIR, "pd_%s.json.gz" % date)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False)
    print("[snapshot] %s  %.1f MB" % (path, os.path.getsize(path) / 1e6))
    print("   %s" % json.dumps(snap["counts"]))


if __name__ == "__main__":
    main()
