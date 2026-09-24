#!/usr/bin/env python3
"""P0-2 step 3 (option 3) - compute the TRUE gap set, replay only genuine gaps.

WHY NOT JUST REPLAY THE SPAN: "dedupe absorbs the overlap" only holds inside
`dedupe_max_age_sec` (48h). This span reaches back 10 days, so most rows would be REPROCESSED,
not absorbed - ~1,100 live executions to repair a smaller real gap.

TRUE GAP = a SENT row whose (person, campaign) has no Pipedrive lead. Matching follows W1.0.11:
lead Campaign field exact, else '{campaign_id} - ' title prefix (Make leaves the Campaign field
empty, so the fallback is load-bearing).

Person lookups are person-SCOPED (`/v1/leads?person_id=`), not the global 500-row page - the audit's
Finding 4. Reads are rate-limited and cached; another session may be spending the same API budget.

Reports three numbers: rows in span / already have CRM records / actually replayed.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WEBHOOK = "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}"
SL_INBOX = "https://app.smartlead.ai/app/master-inbox?leadMap="
F_LEAD_CAMPAIGN = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
BOUNDS = {
    3686181: ("[Events Visiting] AI4 2026 - Mario - Valids", "2026-07-31T17:43:14Z"),
    3686184: ("[Events Visiting] AI4 2026 - Mario - Catch-alls", "2026-08-04T14:07:32Z"),
    3686187: ("[Events Visiting] AI4 2026 - Rune - Valids", "2026-08-04T14:07:27Z"),
    3686193: ("[Events Visiting] AI4 2026 - Rune - Catch-alls", "2026-08-04T14:07:42Z"),
}
PD_SLEEP = float(os.environ.get("PD_SLEEP", "0.35"))     # gentle: shared API budget
BATCH, PAUSE = 20, 12


def ts(s):
    if not s:
        return None
    raw = str(s)
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get(url, headers, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(6 * (i + 1)); continue
            return {"__err": e.code}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(4); continue
            return {"__err": str(e)[:100]}
    return {}


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                {"User-Agent": "janea-gap/1.0"})


def pd(p):
    time.sleep(PD_SLEEP)
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea-gap/1.0"})


def post(body):
    try:
        r = urllib.request.Request(WEBHOOK, data=json.dumps(body).encode(), method="POST",
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return x.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)[:60]


def canon(s):
    return " ".join(str(s or "").replace(" ", " ").split())


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# ---------------------------------------------------------------- 1. rows in span
rows = []
for cid, (cname, since_s) in BOUNDS.items():
    since = ts(since_s)
    skip, pages = 0, 0
    while pages < 40:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            print(f"  campaign {cid}: ERROR {page['__err']}"); break
        pages += 1
        for row in (page.get("data") or []):
            for h in (row.get("history") or []):
                if str(h.get("type", "")).upper() != "SENT":
                    continue
                t = ts(h.get("time"))
                if not t or t < since:
                    continue
                rows.append({"campaign_id": cid, "campaign_name": cname,
                             "lead_id": row.get("lead_id"),
                             "to": str(row.get("to") or "").lower(),
                             "from": row.get("from"), "map_id": row.get("email_lead_map_id"),
                             "seq": h.get("email_seq_number"), "subject": h.get("subject"),
                             "stats_id": h.get("stats_id"), "time": t.isoformat()})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.05)
print(f"[1] rows in span: {len(rows)}")

# one representative row per (email, campaign) - a lead is per person+campaign, not per send
pairs = {}
for r in rows:
    k = (r["to"], r["campaign_id"])
    if k not in pairs or r["time"] < pairs[k]["time"]:
        pairs[k] = r
print(f"    distinct (person, campaign) pairs: {len(pairs)}")

# ---------------------------------------------------------------- 2. does a lead exist?
# CHECKPOINT. This read pass takes ~10 minutes and has already been killed once by a process exit,
# losing 50 pairs of work. Progress is flushed to disk every 25 pairs and reloaded on restart - a
# long job must not depend on its own process surviving (same lesson as the finally-restore).
CKPT = os.path.join(HERE, "wf1-release-evidence", "p05c_checkpoint.json")
person_cache, leads_cache = {}, {}
gaps, have, done_keys = [], [], set()
if os.path.exists(CKPT):
    _c = json.load(open(CKPT, encoding="utf-8"))
    person_cache = _c.get("person_cache") or {}
    gaps, have = _c.get("gaps") or [], _c.get("have") or []
    done_keys = {tuple(k) for k in (_c.get("done") or [])}
    print(f"    resuming from checkpoint: {len(done_keys)} pairs already checked "
          f"(gaps={len(gaps)} have={len(have)})")


def _save(done):
    json.dump({"person_cache": person_cache, "gaps": gaps, "have": have,
               "done": [list(k) for k in done]},
              open(CKPT, "w", encoding="utf-8"), ensure_ascii=False, default=str)


for i, ((email, cid), r) in enumerate(sorted(pairs.items()), 1):
    if (email, cid) in done_keys:
        continue
    if email not in person_cache:
        s = pd(f"/v1/persons/search?term={urllib.parse.quote(email)}&fields=email"
               f"&exact_match=true")
        items = ((s or {}).get("data") or {}).get("items") or []
        person_cache[email] = items[0]["item"]["id"] if items else None
    pid = person_cache[email]
    if pid is None:
        gaps.append({**r, "why": "no person"})
    else:
        if pid not in leads_cache:
            d = pd(f"/v1/leads?limit=100&person_id={pid}&archived_status=all")
            leads_cache[pid] = (d or {}).get("data") or []
        found = None
        for L in leads_cache[pid]:
            if canon(L.get(F_LEAD_CAMPAIGN)) == canon(r["campaign_name"]):
                found = L; break
            if str(L.get("title") or "").startswith(f"{cid} - "):
                found = L; break
        (have if found else gaps).append({**r, "person_id": pid,
                                          "lead_id_pd": (found or {}).get("id"),
                                          "why": None if found else "person, no lead"})
    done_keys.add((email, cid))
    if i % 25 == 0:
        _save(done_keys)
    if i % 50 == 0:
        print(f"    ...{i}/{len(pairs)} pairs checked  gaps={len(gaps)} have={len(have)}",
              flush=True)
_save(done_keys)

print(f"\n[2] already have CRM records : {len(have)}")
print(f"    TRUE GAPS                : {len(gaps)}")
from collections import Counter
print(f"    gap reasons              : {dict(Counter(g['why'] for g in gaps))}")
print(f"    gaps per campaign        : "
      f"{dict(Counter(g['campaign_name'].split(' - ')[-1] for g in gaps))}")

if not a.deploy:
    print(f"\n--deploy not given: nothing replayed.")
    print(f"  would replay {len(gaps)} genuine gaps "
          f"(vs {len(rows)} rows in span - {len(rows) - len(gaps)} avoided)")
    json.dump({"rows_in_span": len(rows), "pairs": len(pairs), "have": len(have),
               "gaps": gaps}, open(os.path.join(HERE, "wf1-release-evidence",
                                                "p05c_gapset.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False, default=str)
    sys.exit(0)

print(f"\n[3] replaying {len(gaps)} genuine gaps, batches of {BATCH}, {PAUSE}s pause\n")
sent, failed = 0, []
for i, r in enumerate(gaps, 1):
    body = {"event_type": "EMAIL_SENT", "campaign_id": r["campaign_id"],
            "campaign_name": r["campaign_name"], "lead_id": r["lead_id"],
            "sl_email_lead_id": r["lead_id"], "sl_email_lead_map_id": r["map_id"],
            "app_url": (SL_INBOX + str(r["map_id"])) if r["map_id"] else None,
            "to_email": r["to"], "from_email": r["from"],
            "sequence_number": int(r["seq"]) if str(r["seq"] or "").isdigit() else 1,
            "timestamp": r["time"], "time_sent": r["time"], "event_timestamp": r["time"],
            "subject": r["subject"], "stats_id": r["stats_id"],
            "__reconciled": True, "__reconciled_by": "blind-window-gapset"}
    st = post(body)
    if st == 200:
        sent += 1
    else:
        failed.append({"to": r["to"], "time": r["time"], "status": st})
    if i % BATCH == 0:
        print(f"  {i}/{len(gaps)}  accepted={sent} failed={len(failed)}", flush=True)
        time.sleep(PAUSE)

print(f"\nROWS IN SPAN {len(rows)}  |  ALREADY HAVE CRM {len(have)}  |  REPLAYED {sent}")
for f in failed[:10]:
    print(f"   FAILED {f['status']}  {f['to']} {f['time']}")
json.dump({"at": datetime.now(timezone.utc).isoformat(), "rows_in_span": len(rows),
           "pairs": len(pairs), "have": len(have), "gaps": len(gaps), "replayed": sent,
           "failed": failed},
          open(os.path.join(HERE, "wf1-release-evidence", "p05c_gapset.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/p05c_gapset.json")
sys.exit(0 if not failed else 1)
