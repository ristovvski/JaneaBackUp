"""Backfill the WF-1 production gaps found by the 2026-08-04 audit.  DRY-RUN BY DEFAULT.

Priority order is the owner's:
  P1  the invisible conversation - Person-ef1ea617: lead labels + the reply activity carrying the
      reply text (his reply of 2026-07-31T15:31Z never reached the CRM), and the two other
      label-gap leads whose events were lost the same way
  P2  the leads that ACCEPTED  - a real connection with no CRM record
  P3  the invite-only leads    - lowest value, highest volume

NOT backfilled: the 106 pre-production test-campaign touches (13-17 July). Owner decision: accepted
gap, left as-is, recorded in the report for Melisa.

Every write mirrors a WF-1 invariant rather than inventing one:
  * labels are a UNION - existing labels are never removed (W1.0.7)
  * `connected` is only ever set by a real accept, never by a reply (W1.0.9 event-truth)
  * lead titles follow `{campaign.id} - {campaign.name} - {full_name}` and carry the Campaign field
  * empty custom fields and empty activity notes are OMITTED (R4 / W1.0.6)
  * persons resolve by LinkedIn URL, then member_id, then public slug (W1.0.16)

WRITE_MODE=live is required for any write. Nothing here runs without it.
"""
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
ONLY = os.environ.get("ONLY", "")            # P1 | P2 | P3 | "" for all
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
HRK = os.environ["HEYREACH_API_KEY"]
UA = "Mozilla/5.0 janea-backfill/1.0"

F_LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
F_MEMBER = "010fc51128116e8c73ae2b33fd52fd4537451f2b"
F_PUBLIC = "2339d1c7a7cda05651dff68ff82b2d56b20e241d"
F_STAGE = "f016efd8791291c591c1d49440018ab0bd23384d"
F_CONNAT = "b03b86666936a46f063dfff6a922ef884fdefac4"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_MEDIUM = "961698945b0329b367da11916a94f10ff7ba71fe"
F_CAMPAIGN = "86157bb49563191c17b4dc62580525f84417524c"
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONN = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESP = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
MELISA = 16340280
CHANNEL = 578
ACT_TYPE = "linkedin_messaging"
CAMPS = [513000, 512995]
# the three lost-event leads from the audit, and the reply that never landed
P1_LABELS = {
    "Person-ef1ea617": {"add": [L_RESP], "reply_at": "2026-07-31T15:31:57Z"},
    "Andrew Miller-McKeever": {"add": [L_RESP], "reply_at": "2026-07-22T20:45:15Z"},
    "Person-6193c11f": {"add": [L_CONN], "reply_at": None},
}


def pd(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path, data=data,
                                       method=method,
                                       headers={"x-api-token": PDT, "User-Agent": UA,
                                                **({"Content-Type": "application/json"}
                                                   if data else {})})
            with urllib.request.urlopen(r, timeout=180) as x:
                return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            return e.code, b
    return 0, None


def hr(path, body, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.heyreach.io/api/public" + path,
                                       data=json.dumps(body).encode(), method="POST",
                                       headers={"X-API-KEY": HRK, "Accept": "application/json",
                                                "Content-Type": "application/json",
                                                "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


def norm_li(u):
    if not u:
        return None
    s = str(u).strip().lower().split("?")[0].rstrip("/")
    m = re.search(r"/in/([^/]+)$", s)
    return m.group(1) if m else s


def resolve_person(idx, rec):
    """W1.0.16 order: URL, then member_id, then public slug."""
    by_li, by_mem, by_pub = idx
    return (by_li.get(rec["slug"])
            or (by_mem.get(rec["member_key"]) if rec.get("member_key") else None)
            or by_pub.get(rec["slug"]))


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE = {WRITE_MODE!r}  "
          f"({'LIVE - WILL WRITE' if live else 'dry run, no writes'})   ONLY={ONLY or 'all'}")

    # ---- HeyReach truth
    truth = {}
    for cid in CAMPS:
        off = 0
        while True:
            d = hr("/campaign/GetLeadsFromCampaign",
                   {"campaignId": cid, "offset": off, "limit": 100})
            its = (d or {}).get("items") or []
            for L in its:
                p = L.get("linkedInUserProfile") or {}
                slug = norm_li(p.get("profileUrl"))
                if not slug:
                    continue
                conn = str(L.get("leadConnectionStatus") or "")
                msg = str(L.get("leadMessageStatus") or "")
                truth[(slug, cid)] = {
                    "slug": slug, "member_key": str(p.get("linkedin_id") or "") or None,
                    "campaign_id": cid,
                    "name": f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip(),
                    "company": p.get("companyName"), "position": p.get("position"),
                    "location": p.get("location"), "email": p.get("emailAddress"),
                    "profile": p.get("profileUrl"), "summary": p.get("about"),
                    "contacted": conn in ("ConnectionSent", "ConnectionAccepted")
                    or msg in ("MessageSent", "MessageReply"),
                    "accepted": conn == "ConnectionAccepted",
                    "replied": msg == "MessageReply",
                    "created": L.get("creationTime"),
                }
            off += len(its)
            if len(its) < 100 or off >= int((d or {}).get("totalCount") or 0):
                break
    names = {c["id"]: c["name"] for c in
             ((hr("/campaign/GetAll", {"offset": 0, "limit": 100}) or {}).get("items") or [])}
    print(f"HeyReach production touches: {sum(1 for r in truth.values() if r['contacted'])}")

    # ---- inbound reply texts (for the P1 activity)
    convs, off = [], 0
    while True:
        d = hr("/inbox/GetConversationsV2",
               {"filters": {"linkedInAccountIds": [], "campaignIds": []},
                "offset": off, "limit": 100})
        its = (d or {}).get("items") or []
        convs.extend(its)
        off += len(its)
        if len(its) < 100 or off >= int((d or {}).get("totalCount") or 0):
            break
    replies = {}
    for cv in convs:
        k = norm_li((cv.get("correspondentProfile") or {}).get("profileUrl"))
        for m in cv.get("messages") or []:
            if str(m.get("sender", "")).upper() != "ME" and str(m.get("body") or "").strip():
                replies.setdefault(k, []).append(m)

    # ---- CRM state
    by_li, by_mem, by_pub, leads_by_person = {}, {}, {}, {}
    cursor = None
    while True:
        st, d = pd("/api/v2/persons?limit=500&sort_by=id&sort_direction=asc"
                   + (f"&cursor={cursor}" if cursor else ""))
        for p in (d.get("data") or []):
            cf = p.get("custom_fields") or {}
            k = norm_li(cf.get(F_LI))
            if k:
                by_li.setdefault(k, p)
            if cf.get(F_MEMBER) not in (None, ""):
                by_mem.setdefault(str(cf[F_MEMBER]), p)
            if cf.get(F_PUBLIC) not in (None, ""):
                for part in str(cf[F_PUBLIC]).lower().split(","):
                    if part.strip():
                        by_pub.setdefault(part.strip(), p)
        cursor = (d.get("additional_data") or {}).get("next_cursor")
        if not cursor:
            break
    start = 0
    while True:
        st, d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
        b = d.get("data") or []
        for L in b:
            if L.get("person_id"):
                leads_by_person.setdefault(L["person_id"], []).append(L)
        more = ((d.get("additional_data") or {}).get("pagination") or {})
        start += len(b)
        if not b or not more.get("more_items_in_collection"):
            break
    idx = (by_li, by_mem, by_pub)
    print(f"CRM index: {len(by_li)} by url, {len(by_mem)} by member_id, {len(by_pub)} by slug")

    # Existing reply text, so we never log the same reply twice. Checked by CONTENT, not by presence
    # of *some* activity - presence-matching is exactly what produced the audit's false pass, and
    # here it would have posted a duplicate activity for a reply that was already logged.
    acts_by_person, acts_by_lead = {}, {}
    start = 0
    while True:
        st, d = pd(f"/v1/activities?limit=500&start={start}&type={ACT_TYPE}&user_id=0")
        b = d.get("data") or []
        for a in b:
            if a.get("person_id"):
                acts_by_person.setdefault(a["person_id"], []).append(a)
            if a.get("lead_id"):
                acts_by_lead.setdefault(str(a["lead_id"]), []).append(a)
        more = ((d.get("additional_data") or {}).get("pagination") or {})
        start += len(b)
        if not b or not more.get("more_items_in_collection"):
            break
    print(f"existing {ACT_TYPE} activities: "
          f"{sum(len(v) for v in acts_by_person.values())} indexed by person")

    def words(t):
        return [w for w in re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower()).split() if len(w) > 3]

    def already_logged(person, lead, msg):
        notes = " || ".join(
            str(a.get("note") or "") for a in
            (acts_by_person.get((person or {}).get("id"), [])
             + acts_by_lead.get(str((lead or {}).get("id")), [])))
        nw = set(words(notes))
        mw = words(msg.get("body"))
        if not mw:
            return True                      # nothing to log
        return (sum(1 for w in mw if w in nw) / len(mw)) >= 0.6

    def find_lead(person, rec):
        if not person:
            return None
        cands = leads_by_person.get(person["id"], [])
        for L in cands:
            if str(L.get(F_LEADCAMP) or "") == names.get(rec["campaign_id"]):
                return L
        pre = f"{rec['campaign_id']} - "
        for L in cands:
            if str(L.get("title") or "").startswith(pre):
                return L
        return None

    # ---- classify
    p1, p2, p3 = [], [], []
    for rec in truth.values():
        if not rec["contacted"]:
            continue
        person = resolve_person(idx, rec)
        lead = find_lead(person, rec)
        if person and lead:
            fix = P1_LABELS.get(rec["name"])
            labs = set(str(x) for x in (lead.get("label_ids") or []))
            want = set(labs)
            if rec["accepted"]:
                want.add(L_CONN)
            if rec["replied"]:
                want.add(L_RESP)
            want.add(L_COLD)
            missing = want - labs
            # only reply messages whose text is NOT already in the CRM
            unlogged = [m for m in (replies.get(rec["slug"]) or [])
                        if not already_logged(person, lead, m)] if rec["replied"] else []
            if missing or unlogged or fix:
                p1.append({"rec": rec, "person": person, "lead": lead,
                           "add_labels": sorted(missing), "reply_msgs": unlogged})
            continue
        (p2 if rec["accepted"] else p3).append({"rec": rec, "person": person, "lead": lead})

    print(f"\nP1 label/activity repairs on existing leads : {len(p1)}")
    print(f"P2 accepted, missing from the CRM           : {len(p2)}")
    print(f"P3 invite-only, missing from the CRM        : {len(p3)}")

    planned = []

    def show(tag, items, limit=4):
        print("\n" + "=" * 96)
        print(tag)
        print("=" * 96)
        for i, it in enumerate(items):
            rec, person, lead = it["rec"], it.get("person"), it.get("lead")
            acts = []
            if it.get("add_labels"):
                acts.append(f"PATCH lead {str(lead.get('id'))[:8]} labels += "
                            f"{[LBL.get(x, x[:8]) for x in it['add_labels']]}")
            if it.get("reply_msgs"):
                acts.append(f"POST activity ({len(it['reply_msgs'])} reply msg(s), text logged)")
            if person is None:
                acts.append("POST person (LinkedIn URL + member_id + public_id + Medium)")
            if lead is None:
                acts.append(f"POST lead '{rec['campaign_id']} - {names.get(rec['campaign_id'])} "
                            f"- {rec['name']}' labels="
                            f"{['cold'] + (['connected'] if rec['accepted'] else [])}")
            planned.append({"priority": tag.split()[0], "name": rec["name"],
                            "company": rec.get("company"), "profile": rec.get("profile"),
                            "campaign": names.get(rec["campaign_id"]),
                            "accepted": rec["accepted"], "replied": rec["replied"],
                            "person_id": person["id"] if person else None,
                            "lead_id": lead.get("id") if lead else None,
                            "actions": " | ".join(acts)})
            if i < limit:
                print(f"  {rec['name']} ({rec.get('company')})")
                for a in acts:
                    print(f"      {a}")
        if len(items) > limit:
            print(f"  ... and {len(items) - limit} more (full list in the CSV)")

    LBL = {L_COLD: "cold", L_CONN: "connected", L_RESP: "responded"}
    if ONLY in ("", "P1"):
        show("P1 the invisible conversations", p1)
    if ONLY in ("", "P2"):
        show("P2 accepted connections with no CRM record", p2)
    if ONLY in ("", "P3"):
        show("P3 invite-only touches with no CRM record", p3)

    path = os.path.join(OUT, "wf1_backfill_plan.csv")
    if planned:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(planned[0].keys()))
            w.writeheader()
            w.writerows(planned)
        print(f"\nwrote {path} ({len(planned)} planned rows)")

    if not live:
        print("\nDRY RUN COMPLETE - nothing was written.")
        print("To execute, per priority:  WRITE_MODE=live ONLY=P1  (then P2, then P3)")
        return 0

    # ------------------------------------------------------------------ live
    print("\n" + "=" * 96)
    print("LIVE EXECUTION")
    print("=" * 96)
    done = fail = 0
    groups = ([("P1", p1)] if ONLY in ("", "P1") else []) \
        + ([("P2", p2)] if ONLY in ("", "P2") else []) \
        + ([("P3", p3)] if ONLY in ("", "P3") else [])
    for tag, items in groups:
        for it in items:
            rec, person, lead = it["rec"], it.get("person"), it.get("lead")
            try:
                if it.get("add_labels"):
                    labs = list({*(str(x) for x in (lead.get("label_ids") or [])),
                                 *it["add_labels"]})          # UNION, never removes (W1.0.7)
                    st, r = pd(f"/v1/leads/{lead['id']}", "PATCH", {"label_ids": labs})
                    print(f"  {tag} lead {str(lead['id'])[:8]} labels -> {st}")
                    if st >= 300:
                        raise RuntimeError(r)
                for m in it.get("reply_msgs") or []:
                    note = str(m.get("body") or "").strip()
                    body = {"subject": f"LinkedIn reply: {rec['name']}",
                            "type": ACT_TYPE, "done": True, "user_id": MELISA,
                            "lead_id": str(lead["id"]), "person_id": person["id"]}
                    if note:                                   # W1.0.6 omit empty note
                        body["note"] = note
                    st, r = pd("/api/v2/activities", "POST", body)
                    print(f"  {tag} reply activity for {rec['name']} -> {st}")
                    if st >= 300:
                        raise RuntimeError(r)
                if person is None:
                    cf = {F_LI: rec["profile"], F_MEDIUM: "LinkedIn",
                          F_CAMPAIGN: names.get(rec["campaign_id"]),
                          F_STAGE: "Accepted" if rec["accepted"] else "Invited"}
                    if rec.get("member_key"):
                        cf[F_MEMBER] = int(rec["member_key"])
                    if rec.get("slug"):
                        cf[F_PUBLIC] = rec["slug"]
                    for k in ("company", "position", "location"):
                        pass
                    cf = {k: v for k, v in cf.items() if v not in (None, "")}   # R4
                    body = {"name": rec["name"], "owner_id": MELISA, "custom_fields": cf}
                    if rec.get("email"):
                        body["emails"] = [{"value": rec["email"], "primary": True,
                                           "label": "work"}]
                    st, r = pd("/api/v2/persons", "POST", body)
                    if st >= 300:
                        raise RuntimeError(r)
                    person = r.get("data") or {}
                    print(f"  {tag} person {person.get('id')} created for {rec['name']}")
                if lead is None:
                    labels = [L_COLD] + ([L_CONN] if rec["accepted"] else [])
                    body = {"title": f"{rec['campaign_id']} - {names.get(rec['campaign_id'])} "
                                     f"- {rec['name']}",
                            "person_id": person["id"], "owner_id": MELISA,
                            "channel": CHANNEL, "label_ids": labels,
                            F_LEADCAMP: names.get(rec["campaign_id"])}
                    st, r = pd("/v1/leads", "POST", body)
                    if st >= 300:
                        raise RuntimeError(r)
                    print(f"  {tag} lead {str((r.get('data') or {}).get('id'))[:8]} created "
                          f"for {rec['name']}")
                done += 1
            except Exception as e:                              # noqa: BLE001
                fail += 1
                print(f"  {tag} FAILED {rec['name']}: {str(e)[:200]}")
    print(f"\ncompleted {done}, failed {fail}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
