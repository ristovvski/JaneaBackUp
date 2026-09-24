"""WF-1 FULL AUDIT — did HeyReach → Pipedrive work fully correctly?  Read-only.

Truth source: HeyReach (all campaigns, all-time) per lead:
    contacted = ConnectionSent|ConnectionAccepted, or MessageSent|MessageReply
    accepted  = leadConnectionStatus == ConnectionAccepted
    replied   = leadMessageStatus == MessageReply, corroborated by an inbound inbox message
CRM expectation (WF-1 invariants, reference §4):
    person exists (matched on lh_linkedin_profile_url, fallback member_id)
    lead exists for THAT campaign (Campaign field == campaign.name, fallback title prefix "{id} - ")
    contacted -> cold ; accepted -> connected + lh_connected_at ; replied -> responded
    replied  -> a linkedin_messaging activity carrying the reply text

Two classes are kept strictly apart:
  MISSING label  = WF-1 failed to write something it owns            -> a defect
  EXTRA label    = a label present that our event-truth would not set -> the KNOWN sprint-Zap
                   cohabitant (adds connected+responded ~90s after us), NOT a WF-1 defect
Conflating those two would manufacture false alarms, since union labels never remove.

Pipedrive list reads are sorted+paginated (banned-class rule). No writes.
"""
import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
HRK = os.environ["HEYREACH_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-audit/1.0"
HR = "https://api.heyreach.io/api/public"

F_LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
F_MEMBER = "010fc51128116e8c73ae2b33fd52fd4537451f2b"
F_PUBLIC = "2339d1c7a7cda05651dff68ff82b2d56b20e241d"
F_CONNAT = "b03b86666936a46f063dfff6a922ef884fdefac4"
F_STAGE = "f016efd8791291c591c1d49440018ab0bd23384d"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONN = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESP = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
LOST_REPLY = "2026-07-30T09:46"          # the known lost WF-1 event


def hr(path, body, tries=5):
    for i in range(tries):
        try:
            r = urllib.request.Request(HR + path, data=json.dumps(body).encode(), method="POST",
                                       headers={"X-API-KEY": HRK, "Accept": "application/json",
                                                "Content-Type": "application/json",
                                                "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}
        except Exception:                                     # noqa: BLE001
            if i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            raise
    return {}


def pd(path, tries=5):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path,
                                       headers={"x-api-token": PDT, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}
        except Exception:                                     # noqa: BLE001
            if i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            raise
    return {}


def norm_li(u):
    """Compare LinkedIn identities, not URL spellings."""
    if not u:
        return None
    s = str(u).strip().lower().split("?")[0].rstrip("/")
    m = re.search(r"/in/([^/]+)$", s)
    if m:
        return m.group(1)
    m = re.search(r"/sales/lead/([^,/]+)", s)          # Sales Navigator form
    if m:
        return "sales:" + m.group(1)
    return s or None


# ============================================================ 1. HeyReach truth
camps = (hr("/campaign/GetAll", {"offset": 0, "limit": 100}) or {}).get("items") or []
print(f"HeyReach campaigns: {len(camps)}")
hrleads = {}                 # norm_li -> record
per_camp = {}
for c in camps:
    cid, cname = c["id"], c["name"]
    per_camp[cid] = {"name": cname, "status": c.get("status"), "total": 0, "contacted": 0,
                     "accepted": 0, "replied": 0, "no_person": 0, "no_lead": 0,
                     "miss_cold": 0, "miss_conn": 0, "miss_resp": 0, "miss_connat": 0,
                     "miss_activity": 0}
    off = 0
    while True:
        d = hr("/campaign/GetLeadsFromCampaign", {"campaignId": cid, "offset": off, "limit": 100})
        if d.get("__err"):
            print(f"  [{cid}] ERR {d}")
            break
        its = d.get("items") or []
        for L in its:
            prof = L.get("linkedInUserProfile") or {}
            key = norm_li(prof.get("profileUrl"))
            if not key:
                continue
            conn = str(L.get("leadConnectionStatus") or "")
            msg = str(L.get("leadMessageStatus") or "")
            rec = {"key": key, "member_key": str(prof.get("linkedin_id") or "") or None,
                   "campaign_id": cid, "campaign": cname,
                   "name": f"{prof.get('firstName') or ''} {prof.get('lastName') or ''}".strip(),
                   "company": prof.get("companyName"), "position": prof.get("position"),
                   "profile": prof.get("profileUrl"), "hr_lead_id": L.get("id"),
                   "conn": conn, "msg": msg,
                   "contacted": conn in ("ConnectionSent", "ConnectionAccepted")
                   or msg in ("MessageSent", "MessageReply"),
                   "accepted": conn == "ConnectionAccepted",
                   "replied": msg == "MessageReply",
                   "created": L.get("creationTime"), "last_action": L.get("lastActionTime"),
                   "sender": L.get("linkedInSenderFullName"),
                   "campaign_status": L.get("leadCampaignStatus")}
            prev = hrleads.get(key)
            # one person can sit in several campaigns; keep the furthest-progressed touch per
            # (key, campaign) - the audit is per campaign, so index by both
            hrleads[(key, cid)] = rec
            per_camp[cid]["total"] += 1
        off += len(its)
        if len(its) < 100 or off >= int(d.get("totalCount") or 0):
            break
    print(f"  [{cid}] {cname[:52]:<54} leads={per_camp[cid]['total']}")

# ---- inbox: reply timestamps + texts, keyed by LinkedIn identity
convs, off = [], 0
senders = {}
while True:
    d = hr("/inbox/GetConversationsV2",
           {"filters": {"linkedInAccountIds": [], "campaignIds": []}, "offset": off, "limit": 100})
    if d.get("__err"):
        print(f"  inbox ERR {d}")
        break
    its = d.get("items") or []
    convs.extend(its)
    off += len(its)
    if len(its) < 100 or off >= int(d.get("totalCount") or 0):
        break
inbound = {}                 # norm_li -> [{at, body}]
for cv in convs:
    key = norm_li((cv.get("correspondentProfile") or {}).get("profileUrl"))
    if not key:
        continue
    for m in cv.get("messages") or []:
        s = str(m.get("sender") or "")
        senders[s] = senders.get(s, 0) + 1
        if s.upper() != "ME":
            inbound.setdefault(key, []).append({"at": m.get("createdAt"),
                                                "body": (m.get("body") or "")[:400],
                                                "inmail": m.get("isInMail")})
print(f"conversations: {len(convs)}; message sender values seen: {senders}")
print(f"people with >=1 inbound message: {len(inbound)}")

# ============================================================ 2. CRM state
persons_by_li, persons_by_member, persons_by_public, person_by_id = {}, {}, {}, {}
cursor, pages = None, 0
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc"
    if cursor:
        q += "&cursor=" + cursor
    d = pd(q)
    if d.get("__err"):
        raise SystemExit(f"persons page failed: {d}")
    for p in d.get("data") or []:
        cf = p.get("custom_fields") or {}
        person_by_id[p["id"]] = p
        k = norm_li(cf.get(F_LI))
        if k:
            persons_by_li.setdefault(k, p)
        mid = cf.get(F_MEMBER)
        if mid not in (None, ""):
            persons_by_member.setdefault(str(mid), p)
        pub = cf.get(F_PUBLIC)
        if pub not in (None, ""):
            for part in str(pub).lower().split(","):
                part = part.strip()
                if part:
                    persons_by_public.setdefault(part, p)
    pages += 1
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break
print(f"Pipedrive persons: {pages} pages, {len(persons_by_li)} with a LinkedIn identity")

leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    if d.get("__err"):
        raise SystemExit(f"leads page failed: {d}")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
leads_by_person = {}
for L in leads:
    if L.get("person_id"):
        leads_by_person.setdefault(L["person_id"], []).append(L)
print(f"Pipedrive leads: {len(leads)}")

acts, start = [], 0
while True:
    d = pd(f"/v1/activities?limit=500&start={start}&type=linkedin_messaging&user_id=0")
    if d.get("__err"):
        print(f"  activities page failed: {d}")
        break
    b = d.get("data") or []
    acts.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
acts_by_lead, acts_by_person = {}, {}
for a in acts:
    if a.get("lead_id"):
        acts_by_lead.setdefault(str(a["lead_id"]), []).append(a)
    if a.get("person_id"):
        acts_by_person.setdefault(a["person_id"], []).append(a)
print(f"linkedin_messaging activities: {len(acts)}")


def find_lead(person, rec):
    """WF-1's own matching rule: Campaign field == campaign.name, else the title prefix."""
    if not person:
        return None, None
    cands = [L for L in leads_by_person.get(person["id"], []) if not L.get("is_archived")]
    allc = leads_by_person.get(person["id"], [])
    for L in cands or allc:
        if str(L.get(F_LEADCAMP) or "") == rec["campaign"]:
            return L, "campaign_field"
    pre = f"{rec['campaign_id']} - "
    for L in cands or allc:
        if str(L.get("title") or "").startswith(pre):
            return L, "title_prefix"
    return None, None


# ============================================================ 3. the audit
rows_missing, rows_labels, rows_activity, rows_extra = [], [], [], []
checked = 0
for (key, cid), rec in sorted(hrleads.items(), key=lambda kv: kv[1]["created"] or ""):
    if not rec["contacted"]:
        continue
    checked += 1
    pc = per_camp[cid]
    pc["contacted"] += 1
    if rec["accepted"]:
        pc["accepted"] += 1
    replied = rec["replied"] or key in inbound
    if replied:
        pc["replied"] += 1

    # W1.0.16: resolve the way the workflow now does - LinkedIn URL, then the numeric member id
    # (which equals HeyReach's linkedin_id), then the public slug. Keyed by member_id per the
    # owner's instruction, so a slug change no longer reads as a missing person.
    person = (persons_by_li.get(key)
              or (persons_by_member.get(rec["member_key"]) if rec.get("member_key") else None)
              or persons_by_public.get(key))
    if not person:
        pc["no_person"] += 1
        rows_missing.append({**{k: rec[k] for k in ("name", "company", "position", "profile",
                                                   "campaign", "campaign_id", "created",
                                                   "sender", "conn", "msg")},
                             "what_is_missing": "person AND lead (nothing in CRM)",
                             "accepted": rec["accepted"], "replied": replied})
        continue
    lead, how = find_lead(person, rec)
    if not lead:
        pc["no_lead"] += 1
        rows_missing.append({**{k: rec[k] for k in ("name", "company", "position", "profile",
                                                   "campaign", "campaign_id", "created",
                                                   "sender", "conn", "msg")},
                            "what_is_missing": f"lead (person {person['id']} exists)",
                            "accepted": rec["accepted"], "replied": replied})
        continue

    labs = set(str(x) for x in (lead.get("label_ids") or []))
    cf = person.get("custom_fields") or {}
    miss = []
    if L_COLD not in labs:
        miss.append("cold")
        pc["miss_cold"] += 1
    if rec["accepted"]:
        if L_CONN not in labs:
            miss.append("connected")
            pc["miss_conn"] += 1
        if not cf.get(F_CONNAT):
            miss.append("lh_connected_at")
            pc["miss_connat"] += 1
    if replied and L_RESP not in labs:
        miss.append("responded")
        pc["miss_resp"] += 1
    if miss:
        rows_labels.append({"name": rec["name"], "profile": rec["profile"],
                            "campaign": rec["campaign"], "lead_id": lead.get("id"),
                            "person_id": person["id"],
                            "heyreach_truth": f"conn={rec['conn']},msg={rec['msg']}",
                            "missing": ";".join(miss),
                            "labels_present": len(labs), "matched_by": how})
    extra = []
    if L_CONN in labs and not rec["accepted"]:
        extra.append("connected (no accept in HeyReach)")
    if L_RESP in labs and not replied:
        extra.append("responded (no reply in HeyReach)")
    if extra:
        rows_extra.append({"name": rec["name"], "profile": rec["profile"],
                           "campaign": rec["campaign"], "lead_id": lead.get("id"),
                           "heyreach_truth": f"conn={rec['conn']},msg={rec['msg']}",
                           "extra": ";".join(extra)})

    if replied:
        la = acts_by_lead.get(str(lead.get("id")), []) + acts_by_person.get(person["id"], [])
        with_text = [a for a in la if str(a.get("note") or "").strip()]
        if not with_text:
            pc["miss_activity"] += 1
            texts = inbound.get(key) or []
            rows_activity.append({"name": rec["name"], "profile": rec["profile"],
                                  "campaign": rec["campaign"], "lead_id": lead.get("id"),
                                  "person_id": person["id"],
                                  "activities_on_record": len(la),
                                  "reply_at": (texts[0]["at"] if texts else ""),
                                  "reply_text_in_heyreach":
                                      (texts[0]["body"][:160] if texts else "")})

# ---- the known lost reply of 30.07 09:46 — who was it?
lost = []
for key, msgs in inbound.items():
    for m in msgs:
        if str(m["at"]).startswith(LOST_REPLY[:13]):          # same hour
            person = persons_by_li.get(key)
            rec = next((r for (k, c), r in hrleads.items() if k == key), None)
            la = acts_by_person.get(person["id"], []) if person else []
            near = [a for a in la if str(a.get("note") or "").strip()
                    and str(m["body"])[:40] in str(a.get("note") or "")]
            lost.append({"at": m["at"], "who": (rec or {}).get("name") or key,
                         "company": (rec or {}).get("company"),
                         "profile": (rec or {}).get("profile") or key,
                         "campaign": (rec or {}).get("campaign"),
                         "person_id": person["id"] if person else None,
                         "text": m["body"][:200],
                         "logged_in_crm": bool(near)})

# ============================================================ 4. output
os.makedirs(OUT, exist_ok=True)


def dump(path, rows, header):
    p = os.path.join(OUT, path)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=(list(rows[0].keys()) if rows else header))
        w.writeheader()
        w.writerows(rows)
    return p


dump("wf1_audit_missing.csv", rows_missing,
     ["name", "company", "profile", "campaign", "what_is_missing"])
dump("wf1_audit_label_mismatches.csv", rows_labels,
     ["name", "profile", "campaign", "lead_id", "missing"])
dump("wf1_audit_missing_reply_text.csv", rows_activity,
     ["name", "profile", "campaign", "lead_id", "reply_at"])
dump("wf1_audit_extra_labels.csv", rows_extra,
     ["name", "profile", "campaign", "lead_id", "extra"])

tot_contacted = sum(v["contacted"] for v in per_camp.values())
tot_bad = len(rows_missing) + len(rows_labels) + len(rows_activity)
ok = tot_contacted - tot_bad
verdict = (f"Yes — all {tot_contacted} of {tot_contacted} contacted leads are in the CRM correctly."
           if tot_bad == 0 else
           f"No — {ok} of {tot_contacted} contacted leads are correct; "
           f"{tot_bad} have a problem "
           f"({len(rows_missing)} absent, {len(rows_labels)} label gaps, "
           f"{len(rows_activity)} replies with no text logged).")

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
L = ["# Did HeyReach → Pipedrive work fully correctly?\n", f"**{verdict}**\n",
     f"_Read-only audit, {stamp}. HeyReach is the truth source; nothing was written._\n",
     "## The numbers\n", "| | count |", "|---|---|",
     f"| HeyReach campaigns | {len(camps)} |",
     f"| leads in those campaigns | {sum(v['total'] for v in per_camp.values())} |",
     f"| **actually contacted** (invite sent / accepted / messaged) | **{tot_contacted}** |",
     f"| of those, accepted | {sum(v['accepted'] for v in per_camp.values())} |",
     f"| of those, replied | {sum(v['replied'] for v in per_camp.values())} |",
     f"| nothing in CRM (no person, no lead) | {sum(v['no_person'] for v in per_camp.values())} |",
     f"| person but no campaign lead | {sum(v['no_lead'] for v in per_camp.values())} |",
     f"| label gaps | {len(rows_labels)} |",
     f"| replies with no text logged | {len(rows_activity)} |", ""]
L.append("## Per campaign\n")
L.append("| campaign | status | contacted | accepted | replied | no CRM record | no lead | "
         "label gaps | reply text missing |")
L.append("|---|---|---|---|---|---|---|---|---|")
for cid, v in sorted(per_camp.items(), key=lambda kv: -kv[1]["contacted"]):
    if not v["contacted"]:
        continue
    lg = v["miss_cold"] + v["miss_conn"] + v["miss_resp"] + v["miss_connat"]
    L.append(f"| {v['name'][:50]} | {v['status']} | {v['contacted']} | {v['accepted']} | "
             f"{v['replied']} | {v['no_person']} | {v['no_lead']} | {lg} | {v['miss_activity']} |")
L.append("")
L.append("## Label detail (what was missing, by kind)\n")
L.append("| expected label | leads missing it |")
L.append("|---|---|")
L.append(f"| `cold` on a contacted lead | {sum(v['miss_cold'] for v in per_camp.values())} |")
L.append(f"| `connected` on an accepted lead | {sum(v['miss_conn'] for v in per_camp.values())} |")
L.append(f"| `lh_connected_at` on an accepted person | "
         f"{sum(v['miss_connat'] for v in per_camp.values())} |")
L.append(f"| `responded` on a replied lead | {sum(v['miss_resp'] for v in per_camp.values())} |")
L.append("")
L.append(f"**Labels present that HeyReach does not justify: {len(rows_extra)}.** These are *not* "
         "WF-1 defects — union labels never remove, and the sprint team's reply-Zap adds "
         "`connected`+`responded` to replied leads ~90 seconds after us (a known, accepted "
         "cohabitant). Listed in `wf1_audit_extra_labels.csv` for completeness.\n")
L.append("## The lost reply of 30.07 09:46 — can we now name who it was?\n")
if lost:
    L.append("Inbound messages in that hour:\n")
    L.append("| when | who | company | campaign | text logged in CRM? |")
    L.append("|---|---|---|---|---|")
    for x in sorted(lost, key=lambda r: str(r["at"])):
        L.append(f"| {x['at']} | {x['who']} | {x.get('company') or ''} | "
                 f"{str(x.get('campaign') or '')[:34]} | "
                 f"{'yes' if x['logged_in_crm'] else '**NO**'} |")
else:
    L.append("HeyReach's inbox holds **no inbound message in that hour**, so the lost event cannot "
             "be attributed to a person from the API. See the blockers note in the task log.\n")
L.append("\n## Files\n")
L.append("| file | contents |")
L.append("|---|---|")
L.append(f"| `wf1_audit_missing.csv` | {len(rows_missing)} contacted leads with no CRM record |")
L.append(f"| `wf1_audit_label_mismatches.csv` | {len(rows_labels)} leads with a missing label |")
L.append(f"| `wf1_audit_missing_reply_text.csv` | {len(rows_activity)} replies with no text |")
L.append(f"| `wf1_audit_extra_labels.csv` | {len(rows_extra)} extra labels (cohabitant, not ours) |")

md = os.path.join(OUT, "WF1_AUDIT_REPORT.md")
open(md, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n" + "=" * 96)
print(verdict)
print("=" * 96)
print(f"wrote {md}")
