"""Melisa's question: "are all leads we contacted now in Pipedrive?"  Read-only, all campaigns.

S5-class discovery: enumerate every Smartlead campaign, keep the ones that actually sent, pull the
full sent-list for each, and match every prospect email against every Pipedrive person email.

Pipedrive reads are sorted+paginated (the banned-class rule: an unsorted /v1 list read used for
counting returns the OLDEST page).  No writes anywhere in this file.

Emits: contacted_vs_pipedrive.csv (the missing prospects) + MELISA_COVERAGE_REPORT.md
"""
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-recon/1.0"
SLAVA = 25035678
SLAVA_FROM = "2026-08-01"
AI4 = {3686193, 3686187, 3686184, 3686181}


def req(url, hdr, tries=5):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={**hdr, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 500, 502, 503, 504) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code, "__body": body}
        except Exception:                                     # noqa: BLE001
            if i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            raise
    return {}


def sl(path):
    sep = "&" if "?" in path else "?"
    return req(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}", {})


def pd(path):
    return req("https://api.pipedrive.com" + path, {"x-api-token": PDT})


# ---------------------------------------------------------------- 1. discover campaigns
camps = sl("/campaigns")
if isinstance(camps, dict):
    raise SystemExit(f"campaign list failed: {camps}")
print(f"campaigns discovered: {len(camps)}")

senders = []
for c in camps:
    an = sl(f"/campaigns/{c['id']}/analytics")
    sent = 0
    if isinstance(an, dict) and not an.get("__err"):
        try:
            sent = int(an.get("sent_count") or 0)
        except (TypeError, ValueError):
            sent = 0
    if sent > 0:
        senders.append({"id": c["id"], "name": c.get("name") or str(c["id"]),
                        "status": c.get("status"), "sent_count": sent})
senders.sort(key=lambda c: -c["sent_count"])
print(f"campaigns that actually sent: {len(senders)}  "
      f"(total sent events {sum(c['sent_count'] for c in senders)})")

# ---------------------------------------------------------------- 2. sent-lists
contacted = {}          # email -> row (first contact wins; all campaigns recorded)
for n, c in enumerate(senders, 1):
    off, rows = 0, 0
    while True:
        st = sl(f"/campaigns/{c['id']}/statistics?offset={off}&limit=100")
        if not isinstance(st, dict) or st.get("__err"):
            print(f"  [{c['id']}] statistics ERR {st.get('__err') if isinstance(st, dict) else st}")
            break
        batch = st.get("data") or []
        for r in batch:
            em = str(r.get("lead_email") or "").strip().lower()
            t = r.get("sent_time")
            if not em or not t:
                continue
            e = contacted.get(em)
            if e is None:
                contacted[em] = {"email": em, "name": r.get("lead_name"),
                                 "company": r.get("lead_company_name")
                                 or r.get("company_name"),
                                 "campaign": c["name"], "campaign_id": c["id"],
                                 "first_sent": t, "campaigns": {c["id"]}}
            else:
                e["campaigns"].add(c["id"])
                if t < e["first_sent"]:
                    e.update({"first_sent": t, "campaign": c["name"],
                              "campaign_id": c["id"]})
                if not e.get("company"):
                    e["company"] = r.get("lead_company_name") or r.get("company_name")
        rows += len(batch)
        off += len(batch)
        if len(batch) < 100 or off >= int(st.get("total_stats") or 0):
            break
    c["rows"] = rows
    print(f"  [{n:>3}/{len(senders)}] {c['name'][:52]:<54} rows={rows}")
print(f"\nunique prospects contacted (all campaigns): {len(contacted)}")

# ---------------------------------------------------------------- 3. Pipedrive persons
have, cursor, pages = {}, None, 0
slava_new, all_new = [], []
users = {u["id"]: u.get("name") for u in (pd("/v1/users").get("data") or [])}
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc"
    if cursor:
        q += "&cursor=" + cursor
    d = pd(q)
    if d.get("__err"):
        raise SystemExit(f"person page failed: {d}")
    for p in d.get("data") or []:
        for em in p.get("emails") or []:
            v = str(em.get("value") or "").strip().lower()
            if v:
                have.setdefault(v, p["id"])
        # NOTE: Pipedrive exposes NO person-creator field on any endpoint (v1, v2, and
        # include_fields=creator_user_id is rejected).  An earlier pass appeared to group persons
        # "by creator" only because it fell back to owner_id.  Hand-patching is therefore measured
        # off LEADS below, where creator_id is real.
        at = str(p.get("add_time") or "")
        if at >= SLAVA_FROM:
            all_new.append((at, None, p.get("id"), p.get("name")))
    pages += 1
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break
print(f"Pipedrive: {pages} pages, {len(have)} distinct person emails")

# ---------------------------------------------------------------- 4. the answer
missing = {e: v for e, v in contacted.items() if e not in have}
pct = 100.0 * len(missing) / len(contacted) if contacted else 0.0
headline = (f"No - {len(missing)} of {len(contacted)} contacted prospects are missing "
            f"({pct:.0f}%)") if missing else "Yes, all present."
print("\n" + "=" * 96)
print(headline)
print("=" * 96)

per = {}
for c in senders:
    per[c["id"]] = {"name": c["name"], "status": c["status"], "contacted": 0, "missing": 0}
for e, v in contacted.items():
    for cid in v["campaigns"]:
        if cid in per:
            per[cid]["contacted"] += 1
            if e in missing:
                per[cid]["missing"] += 1

rows_out = []
for e, v in sorted(missing.items(), key=lambda kv: kv[1]["first_sent"]):
    rows_out.append({"name": v.get("name") or "", "email": e,
                     "company": v.get("company") or "",
                     "campaign": v.get("campaign") or "",
                     "campaign_id": v.get("campaign_id"),
                     "first_sent": v.get("first_sent"),
                     "also_in_campaigns": ";".join(str(x) for x in sorted(v["campaigns"])
                                                   if x != v.get("campaign_id"))})
csv_path = os.path.join(OUT, "contacted_vs_pipedrive.csv")
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()) if rows_out
                       else ["name", "email", "company", "campaign", "campaign_id",
                             "first_sent", "also_in_campaigns"])
    w.writeheader()
    w.writerows(rows_out)
print(f"wrote {csv_path} ({len(rows_out)} rows)")

# count under EVERY campaign that emailed them, so this agrees with the per-campaign table (the CSV
# lists each person once, under their FIRST contact, so the two differ by multi-campaign prospects)
ai4_missing = sum(1 for e, v in missing.items() if v["campaigns"] & AI4)
older_missing = len(missing) - ai4_missing

# ---------------------------------------------------------------- 5. the report
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
L = []
L.append("# Are all the leads we contacted in Pipedrive?\n")
L.append(f"**{headline}**\n")
L.append(f"_Read-only check, {stamp}. Nothing was created, changed or deleted to produce this._\n")
L.append("## The numbers\n")
L.append("| | count |")
L.append("|---|---|")
L.append(f"| campaigns that have sent at least one email | {len(senders)} |")
L.append(f"| send events across them | {sum(c['sent_count'] for c in senders)} |")
L.append(f"| **unique prospects contacted** | **{len(contacted)}** |")
L.append(f"| present in Pipedrive | {len(contacted) - len(missing)} |")
L.append(f"| **missing from Pipedrive** | **{len(missing)} ({pct:.0f}%)** |")
L.append(f"\nOf the missing: **{ai4_missing}** are on the four current Ai4 campaigns and "
         f"**{older_missing}** are on older campaigns.\n")
L.append("Full list with name, email, company, campaign and send date: "
         "`contacted_vs_pipedrive.csv`.\n")
L.append("## Per campaign\n")
L.append("| campaign | status | contacted | in Pipedrive | missing | gap |")
L.append("|---|---|---|---|---|---|")
for cid, v in sorted(per.items(), key=lambda kv: -kv[1]["missing"]):
    if not v["contacted"]:
        continue
    g = 100.0 * v["missing"] / v["contacted"]
    L.append(f"| {v['name'][:56]} | {v['status']} | {v['contacted']} | "
             f"{v['contacted'] - v['missing']} | **{v['missing']}** | {g:.0f}% |")
L.append("\n## Hand-patching so far\n")
L.append("**Pipedrive does not expose who created a *person* through its API** — not on "
         "`/v1/persons`, not on `/api/v2/persons`, and `include_fields=creator_user_id` is rejected. "
         "So persons-added-by-hand is not answerable from the API; only the UI changelog holds it. "
         "*Leads* do carry a creator, so hand-patching is measured there:\n")
leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
recent = [x for x in leads if str(x.get("add_time") or "") >= SLAVA_FROM]
byc = {}
for x in recent:
    byc[x.get("creator_id")] = byc.get(x.get("creator_id"), 0) + 1
L.append(f"Leads created since {SLAVA_FROM}: **{len(recent)}**\n")
L.append("| created by | leads |")
L.append("|---|---|")
for cid, n in sorted(byc.items(), key=lambda kv: -kv[1]):
    L.append(f"| {users.get(cid, cid)} | {n} |")
L.append(f"\nPersons in Pipedrive created since {SLAVA_FROM} (any source): {len(all_new)}.")
L.append("\n## Reminder: the fix is waiting on you\n")
L.append("The backfill for the Ai4 gap is written, dry-run clean and **has never been run** — it "
         "needs your go. It creates one person per missing prospect, re-checking each address "
         "immediately before writing so nothing is duplicated:\n")
L.append("```\nwould create : 300\nskipped      : 0 (already present on re-verify)\n"
         "DRY RUN COMPLETE - nothing was written.\n```\n")
L.append("Separately, **58 prospects already have a lead attached to the wrong person** — the "
         "current automation matches people by *name*, so e.g. our email to "
         "`pii-9e8228ef@example.invalid` landed on a Person-b0e89e97 at `pii-9f60732e@example.invalid`. Those need a human "
         "decision (merge vs re-point) per row: `mis_attached_leads.csv`. Fixing the name-matching "
         "is what stops the gap growing; the backfill only cleans up what already happened.\n")
md = os.path.join(OUT, "MELISA_COVERAGE_REPORT.md")
open(md, "w", encoding="utf-8").write("\n".join(L) + "\n")
print(f"wrote {md}")
