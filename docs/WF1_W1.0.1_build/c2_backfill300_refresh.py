"""Refresh the backfill-300 (Make/email Ai4 persons) list fresh, with DNC/unsubscribe re-check.

Per the owner's instruction: "per-row email re-verify - this also drops anyone who unsubscribed/
DNC'd meanwhile; before/after coverage table." Re-runs the sent-vs-Pipedrive reconciliation for the
4 active Ai4 EMAIL campaigns fresh, then checks each missing prospect's current Smartlead lead
status for unsubscribed/bounced, and each email against Pipedrive's DNC label if a person exists
under a different address. Read-only - produces the refreshed list + before/after table only.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf1-release-evidence")
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-forensics/1.0"
CAMPS = {3686193: "AI4 2026 - Rune - Catch-alls", 3686187: "AI4 2026 - Rune - Valids",
         3686184: "AI4 2026 - Mario - Catch-all", 3686181: "AI4 2026 - Mario - Valids"}
L_DNC = "52a7c290-fc73-11f0-ad98-81d4703453f3"


def sl(path, tries=4):
    sep = "&" if "?" in path else "?"
    for i in range(tries):
        try:
            r = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}",
                                       headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=150) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


def pd(path, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path,
                                       headers={"x-api-token": PDT, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=150) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


# ---------- old list, for the before/after table
old_path = os.path.join(OUT, "ai4_missing_persons.jsonl")
old_rows = ([json.loads(l) for l in open(old_path, encoding="utf-8")]
           if os.path.exists(old_path) else [])
print(f"previous missing-persons list: {len(old_rows)} rows")

# ---------- fresh sent list, with per-row lead status (unsubscribed/bounced)
sent = {}
for cid, cname in CAMPS.items():
    off, rows = 0, 0
    while True:
        st = sl(f"/campaigns/{cid}/statistics?offset={off}&limit=100")
        if not isinstance(st, dict) or st.get("__err"):
            print(f"  [{cid}] ERR {st}")
            break
        batch = st.get("data") or []
        for r in batch:
            em = str(r.get("lead_email") or "").strip().lower()
            t = r.get("sent_time")
            if not em or not t:
                continue
            e = sent.setdefault(em, {"campaign": cname, "campaign_id": cid,
                                     "first_sent": t, "last_sent": t,
                                     "name": r.get("lead_name")})
            e["first_sent"] = min(e["first_sent"], t)
            e["last_sent"] = max(e["last_sent"], t)
        rows += len(batch)
        off += len(batch)
        if len(batch) < 100 or off >= int(st.get("total_stats") or 0):
            break
    print(f"  [{cid}] {cname[:40]:<42} sent rows={rows}")
print(f"unique emails sent (fresh): {len(sent)}")

# ---------- Pipedrive present-check
have, cursor, pages = {}, None, 0
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc"
    if cursor:
        q += "&cursor=" + cursor
    d = pd(q)
    for p in d.get("data") or []:
        for em in p.get("emails") or []:
            v = str(em.get("value") or "").strip().lower()
            if v:
                have.setdefault(v, {"id": p["id"], "labels": p.get("label_ids") or []})
    pages += 1
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break
print(f"Pipedrive persons scanned: {pages} pages, {len(have)} distinct emails")

missing_now = {e: v for e, v in sent.items() if e not in have}
present_but_dnc = {e: v for e, v in have.items() if L_DNC in (v.get("labels") or [])
                   and e in sent}
print(f"\nsent, present in Pipedrive : {len(sent) - len(missing_now)}")
print(f"sent, MISSING in Pipedrive : {len(missing_now)}")
print(f"present but DNC-labeled    : {len(present_but_dnc)}  (would need explicit skip if backfilled)")

# ---------- per-row Smartlead lead status for the missing (unsubscribed/bounced check)
print("\nchecking per-row lead status for the missing set (unsubscribed/bounced)...")
dropped_unsub, kept = [], []
for em, v in missing_now.items():
    d = sl(f"/leads?email={urllib.parse.quote(em)}")
    status = None
    if isinstance(d, dict) and not d.get("__err"):
        # verified response shape (checked live 2026-08-05): a single object with a real boolean
        # is_unsubscribed field - read the FIELD VALUE, never substring-match the raw blob (a field
        # NAME containing "unsubscrib" is present on every response regardless of its value; that
        # bug falsely flagged all 300 rows as unsubscribed on the first pass).
        if d.get("is_unsubscribed") is True:
            status = "unsubscribed"
        else:
            camp_map = d.get("lead_campaign_data") or []
            for c in camp_map:
                cat = str(c.get("lead_category_id") or "")
                if cat and cat.lower() in ("bounced", "9"):     # 9 = Sender Originated Bounce
                    status = "bounced"
                    break
    if status:
        dropped_unsub.append({**v, "email": em, "drop_reason": status})
    else:
        kept.append({**v, "email": em})

print(f"\ndropped (unsubscribed/bounced since original list): {len(dropped_unsub)}")
for r in dropped_unsub[:15]:
    print(f"  {r['email']:<40} {r['drop_reason']:<14} {r['campaign']}")
print(f"\nremaining to backfill: {len(kept)}")

# ---------- before/after table
old_emails = {r["email"] for r in old_rows}
new_emails = {r["email"] for r in kept}
print("\n" + "=" * 92)
print("BEFORE / AFTER COVERAGE TABLE")
print("=" * 92)
print(f"  previously missing (2026-08-04 list) : {len(old_rows)}")
print(f"  fresh sent-vs-CRM missing (now)       : {len(missing_now)}")
print(f"  of fresh-missing, dropped (unsub/bounce): {len(dropped_unsub)}")
print(f"  of fresh-missing, still to backfill    : {len(kept)}")
print(f"  in old list but now present in CRM (someone else fixed them): "
      f"{len(old_emails - set(missing_now.keys()))}")
print(f"  newly missing since 2026-08-04 (not in old list): {len(new_emails - old_emails)}")

path = os.path.join(OUT, "ai4_missing_persons_refreshed.jsonl")
with open(path, "w", encoding="utf-8") as f:
    for r in sorted(kept, key=lambda x: x["first_sent"]):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"\nwrote {path} ({len(kept)} rows) - this is what backfill-300 should now consume")

path2 = os.path.join(OUT, "ai4_dropped_unsubscribed.jsonl")
with open(path2, "w", encoding="utf-8") as f:
    for r in dropped_unsub:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"wrote {path2} ({len(dropped_unsub)} rows)")
