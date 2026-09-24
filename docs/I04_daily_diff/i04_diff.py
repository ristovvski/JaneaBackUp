"""I-04 daily anomaly diff — the five daily checks from the weekly sweep. READ-ONLY.

  1. LEAD DEPARTURES   ids present yesterday, absent today. Each one is detail-read and classified
                       (archived + archive_time, or deleted). This is the check that cannot be
                       reconstructed later: archived leads are invisible to list reads forever.
  2. RECONCILIATION    yesterday - departures + arrivals == today. If it does not close, something
                       moved that neither set explains.
  3. DNC LABEL SET     must equal the expected survivor set exactly, by id, not by count.
  4. NEW PERSONS       created since the prior snapshot, each checked for a duplicate (same email or
                       same LinkedIn slug) against the whole estate.
  5. DANGLERS + 686    activities touched since the prior snapshot whose lead_id is not in today's
                       live set, and the delta in the DNC field-686 population.

USAGE   python i04_diff.py                       # newest two snapshots
        python i04_diff.py --prev 2026-08-19 --curr 2026-08-20

CHECK 1 DEAL-CONVERSION ARM (added 2026-08-27, auditor's flag from the 08-27 run): a lead 404 on
detail read is NOT by itself evidence of loss -- a lead->deal conversion also 404s (the lead record
is gone the moment the deal exists). Verified live 08-27: 13/13 of that day's "DELETED" departures
had an open deal for the same person, created 1-3 SECONDS before the lead's own delete webhook.
Before this fix, Check 1 printed "irreversible, escalate" for every one of them -- indistinguishable
from a real loss on the diff's own output. classify_conversion() is the pure decision function
(unit-testable without any network call -- see test_i04_conversion_static.py, which replays today's
real 13 as fixtures); find_conversion_deal() is the one live read it needs (persons/{id}/deals,
GET-only, matches this script's own READ-ONLY contract).
"""
import sys, os, json, io, gzip, glob, argparse, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aud

SNAPDIR = r"C:\Users\User\Desktop\Нова папка\audit-artifacts\snapshots"
ART = r"C:\Users\User\Desktop\Нова папка\audit-artifacts"
EXPECTED_DNC = set(json.load(io.open(os.path.join(ART, "prereversal_baseline_FINAL.json"),
                                     encoding="utf-8"))["expected_survivors"])
CONVERSION_TOLERANCE_S = 60


def _parse_pd_dt(s):
    # Pipedrive deal add_time: "YYYY-MM-DD HH:MM:SS", no offset marker. Verified live 08-27
    # against a real matched pair (deal 2250 add_time 11:06:14 vs lead-delete webhook
    # meta.timestamp 11:06:15.025Z, 1s apart) -- for this account the value is effectively already
    # UTC, safe to parse as such. Not an assumption: checked against a real cross-referenced pair.
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _parse_iso_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def classify_conversion(deal_add_time, window_start_iso, window_end_iso,
                         delete_ts_iso=None, tolerance_s=CONVERSION_TOLERANCE_S):
    """Pure, network-free. Returns an evidence dict or None. Two tiers, weakest-wins-nothing:
    'timestamp' (strong) -- a real delete-webhook timestamp is known and the deal was created
    within tolerance_s seconds of it, matching the verified 1-3s pattern exactly.
    'window' (weaker, the only option for departures inside an un-snapshotted gap with no webhook
    record) -- the deal was created sometime inside the diff's own snapshot window. Still real
    evidence a conversion happened, not a guess -- but does not pin the exact moment."""
    if not deal_add_time:
        return None
    try:
        dt = _parse_pd_dt(deal_add_time)
    except ValueError:
        return None
    if delete_ts_iso:
        try:
            delta = abs((dt - _parse_iso_dt(delete_ts_iso)).total_seconds())
            if delta <= tolerance_s:
                return {"match": "timestamp", "delta_s": delta}
        except ValueError:
            pass
    if window_start_iso and window_end_iso:
        try:
            if _parse_iso_dt(window_start_iso) <= dt <= _parse_iso_dt(window_end_iso):
                return {"match": "window"}
        except ValueError:
            pass
    return None


def find_conversion_deal(person_id, window_start_iso, window_end_iso, delete_ts_iso=None):
    """One READ-ONLY call per departed-and-404'd lead (bounded: only ever as many as Check 1's own
    'deleted' count, never a bulk scan). Tolerant of failure -- a person lookup miss must not crash
    the whole diff; it just means this departure stays classified as a real, unexplained loss."""
    if person_id is None:
        return None
    try:
        deals = aud.pd("/v1/persons/%s/deals" % person_id).get("data") or []
    except aud.HttpErr:
        return None
    best = None
    for d in deals:
        ev = classify_conversion(d.get("add_time"), window_start_iso, window_end_iso, delete_ts_iso)
        if ev and (best is None or ev["match"] == "timestamp"):
            best = dict(ev, deal_id=d.get("id"), add_time=d.get("add_time"),
                        stage_id=d.get("stage_id"), value=d.get("value"))
            if ev["match"] == "timestamp":
                break
    return best


def load(date):
    with gzip.open(os.path.join(SNAPDIR, "pd_%s.json.gz" % date), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev")
    ap.add_argument("--curr")
    a = ap.parse_args()
    have = sorted(os.path.basename(p)[3:-8] for p in glob.glob(os.path.join(SNAPDIR, "pd_*.json.gz")))
    if len(have) < 2 and not (a.prev and a.curr):
        print("need two snapshots; have %s" % have)
        return
    prev_d, curr_d = (a.prev or have[-2]), (a.curr or have[-1])
    A, B = load(prev_d), load(curr_d)
    print("=" * 96)
    print("I-04 DAILY DIFF   %s -> %s" % (prev_d, curr_d))
    print("   prior : %s" % json.dumps(A["counts"]))
    print("   today : %s" % json.dumps(B["counts"]))
    out = {"prev": prev_d, "curr": curr_d, "prev_counts": A["counts"], "curr_counts": B["counts"]}

    # ---------------- 1 + 2
    la, lb = set(A["leads"]), set(B["leads"])
    gone, new = sorted(la - lb), sorted(lb - la)
    print("\n" + "=" * 96)
    print("1. LEAD DEPARTURES: %d   arrivals: %d" % (len(gone), len(new)))
    dep = []
    window_start = (A.get("captured_at") or (prev_d + "T00:00:00Z"))
    window_end = (B.get("captured_at") or (curr_d + "T23:59:59Z"))
    for lid in gone:
        try:
            d = aud.pd("/v1/leads/" + lid)["data"]
            dep.append({"lead": lid, "archived": d.get("is_archived"),
                        "archive_time": d.get("archive_time"), "person_id": d.get("person_id"),
                        "title": str(d.get("title"))[:70], "owner_id": d.get("owner_id")})
        except aud.HttpErr as e:
            # deal-conversion arm: a 404 read is not by itself evidence of loss -- the same 404
            # fires when the lead became a deal. Recover person_id from YESTERDAY's snapshot (the
            # only place it still exists once the live read 404s) and check for a matching deal.
            prior_person_id = (A["leads"].get(lid) or [None, None, None])[1]
            conv = find_conversion_deal(prior_person_id, window_start, window_end)
            dep.append({"lead": lid, "deleted_http": e.code, "title": None,
                        "person_id": prior_person_id, "converted": conv is not None,
                        "conversion_deal": conv})
        time.sleep(0.1)
    by_day = Counter(str(r.get("archive_time"))[:10] for r in dep if r.get("archived"))
    print("   archived : %d   %s" % (sum(1 for r in dep if r.get('archived')), by_day.most_common()))
    converted = [r for r in dep if r.get("deleted_http") and r.get("converted")]
    lost = [r for r in dep if r.get("deleted_http") and not r.get("converted")]
    print("   CONVERTED: %d  (deal found for the same person -- not a loss)" % len(converted))
    print("   DELETED  : %d  <- irreversible, escalate" % len(lost))
    for r in dep[:12]:
        print("      %s arch=%s at=%s p%s %s" % (r["lead"][:8], r.get("archived"),
              str(r.get("archive_time"))[:19], r.get("person_id"), str(r.get("title"))[:52]))
    if len(dep) > 12:
        print("      ... %d more (all in the artifact)" % (len(dep) - 12))
    for lid in new[:12]:
        print("      NEW %s add=%s p%s" % (lid[:8], str(B["leads"][lid][2])[:19], B["leads"][lid][1]))
    calc = A["counts"]["leads"] - len(gone) + len(new)
    ok = calc == B["counts"]["leads"]
    print("\n2. RECONCILIATION: %d - %d + %d = %d vs %d walked -> %s"
          % (A["counts"]["leads"], len(gone), len(new), calc, B["counts"]["leads"],
             "OK" if ok else "MISMATCH"))
    out["departures"] = dep
    out["arrivals"] = [{"lead": l, "add_time": B["leads"][l][2], "person_id": B["leads"][l][1]} for l in new]
    out["reconciles"] = ok

    # ---------------- 3
    print("\n" + "=" * 96)
    dnc = set(B["dnc_labelled"])
    print("3. DNC LABEL SET: %d labelled | matches the expected survivors exactly: %s"
          % (len(dnc), dnc == EXPECTED_DNC))
    if dnc != EXPECTED_DNC:
        print("   UNEXPECTED: %s" % sorted(dnc - EXPECTED_DNC))
        print("   MISSING   : %s" % sorted(EXPECTED_DNC - dnc))
    out["dnc"] = {"labelled": sorted(dnc), "exact": dnc == EXPECTED_DNC,
                  "unexpected": sorted(dnc - EXPECTED_DNC), "missing": sorted(EXPECTED_DNC - dnc)}

    # ---------------- 4
    print("\n" + "=" * 96)
    pa, pb = A["persons"], B["persons"]
    newp = sorted(set(pb) - set(pa), key=lambda x: pb[x][0] or "")
    print("4. NEW PERSONS: %d" % len(newp))
    by_email, by_slug = defaultdict(list), defaultdict(list)
    for pid, v in pb.items():
        if v[2]:
            by_email[v[2]].append(pid)
        if v[3]:
            by_slug[v[3]].append(pid)
    dups = []
    for pid in newp:
        v = pb[pid]
        e_twins = [x for x in by_email.get(v[2], []) if x != pid]
        s_twins = [x for x in by_slug.get(v[3], []) if x != pid]
        flag = "DUPLICATE" if (e_twins or s_twins) else "ok"
        print("   p%-7s add=%s email=%-34s %s %s" % (pid, str(v[0])[:19], v[2][:34], flag,
              ("email-twins=%s slug-twins=%s" % (e_twins, s_twins)) if flag != "ok" else ""))
        if flag != "ok":
            dups.append({"person": pid, "email": v[2], "slug": v[3],
                         "email_twins": e_twins, "slug_twins": s_twins})
    out["new_persons"] = [{"person": p, "add_time": pb[p][0], "email": pb[p][2]} for p in newp]
    out["new_person_duplicates"] = dups

    # ---------------- 5
    print("\n" + "=" * 96)
    since = (A.get("captured_at") or (prev_d + "T00:00:00Z"))[:19] + "Z"
    acts, cur, pages = [], None, 0
    while pages < 2000:
        pages += 1
        q = {"limit": 100, "updated_since": since}
        if cur:
            q["cursor"] = cur
        r = aud.pd("/api/v2/activities", **q)
        rows = r.get("data") or []
        acts += rows
        cur = (r.get("additional_data") or {}).get("next_cursor")
        if not cur or not rows:
            break
    dang = [{"activity": x.get("id"), "lead": x.get("lead_id"), "type": x.get("type"),
             "done": x.get("done"), "subject": str(x.get("subject"))[:60],
             "add_time": x.get("add_time")}
            for x in acts if x.get("lead_id") and x["lead_id"] not in B["leads"]]
    print("5. DANGLERS: %d activities touched since %s point at a lead not in today's live set"
          % (len(dang), since))
    for d in dang[:14]:
        print("      act %s lead=%s done=%s %r" % (d["activity"], str(d["lead"])[:8], d["done"],
              d["subject"][:44]))
    open_dang = [d for d in dang if d.get("done") is False]
    print("   of those, still OPEN (a task nobody can see): %d  %s"
          % (len(open_dang), [d["activity"] for d in open_dang][:10]))
    pa686, pb686 = A["counts"].get("dnc_field_686"), B["counts"].get("dnc_field_686")
    if pa686 is None or pb686 is None:
        d686 = None
        print("   DNC field-686 population: %s -> %s  (delta NOT COMPUTABLE - one side never "
              "captured the field; a seeded snapshot, not a real zero)" % (pa686, pb686))
    else:
        d686 = pb686 - pa686
        print("   DNC field-686 population: %d -> %d  (delta %+d)" % (pa686, pb686, d686))
    out["danglers"] = dang
    out["open_danglers"] = open_dang
    out["dnc686_delta"] = d686
    out["activities_scanned"] = len(acts)

    # ---------------- verdict
    print("\n" + "=" * 96)
    alerts = []
    if not ok:
        alerts.append("lead count does not reconcile")
    if lost:
        alerts.append("%d lead(s) DELETED, not archived, not converted -- genuine loss" % len(lost))
    if converted:
        print("   (%d of the 404s matched an open deal for the same person -- converted, not lost: %s)"
              % (len(converted), [r["lead"][:8] for r in converted]))
    if dnc != EXPECTED_DNC:
        alerts.append("DNC label set drifted")
    if dups:
        alerts.append("%d new person(s) duplicate an existing record" % len(dups))
    if open_dang:
        alerts.append("%d open task(s) stranded on a departed lead" % len(open_dang))
    if d686:
        alerts.append("DNC field-686 population moved by %+d" % d686)
    if d686 is None:
        alerts.append("DNC field-686 delta unmeasurable (seeded snapshot lacks the field)")
    undeclared = [r for r in dep if r.get("archived")]
    print("VERDICT: %s" % ("; ".join(alerts) if alerts else "no anomalies"))
    print("   (%d archived departures are expected only if an operation declared them - "
          "cross-check against the day's §9f.2 posts)" % len(undeclared))
    out["alerts"] = alerts
    with io.open(os.path.join(ART, "i04_diff_%s.json" % curr_d), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("[wrote] audit-artifacts/i04_diff_%s.json" % curr_d)


if __name__ == "__main__":
    main()
