#!/usr/bin/env python3
"""P0-2 step 3 - backfill the blind SENT window, bounded to the auditor's 4 campaigns.

SCOPE IS DELIBERATELY NARROW. Only the campaigns the auditor bounded, only within their spans.
Cold-ring campaigns carry much larger historical SENT windows (ViVE alone shows 2,761 rows) - those
are Make-era, London-class, and explicitly NOT this job.

METHOD: re-derive the rows from `leads-statistics` `history[] type=SENT` rather than trusting the
15:57Z snapshot, then replay a synthetic EMAIL_SENT into WF-2's webhook - the same payload shape
WF-2S produces, so there is one code path and WF-2's Dedupe absorbs anything already processed.
The dedupe key is now canonicalised on epoch ms, so format differences cannot cause doubles.

METERED: batches with pauses. A ~100-item burst OOM'd this instance on 2026-07-30; that is the
constraint, not a guess.

Every comparison here is TYPED - datetimes parsed, never string-compared (the trap that put 2024
replies in a 2026 window this morning).
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WEBHOOK = "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}"
SL_INBOX = "https://app.smartlead.ai/app/master-inbox?leadMap="

# auditor's per-campaign bounds (a8_handover / CORRECTION 2). Slightly over-inclusive by design:
# the spans start before each campaign's page-500 boundary and WF-2's dedupe absorbs the overlap.
BOUNDS = {
    3686181: ("Mario-Valids", "2026-07-31T17:43:14Z", 306),
    3686184: ("Mario-Catch-alls", "2026-08-04T14:07:32Z", 133),
    3686187: ("Rune-Valids", "2026-08-04T14:07:27Z", 162),
    3686193: ("Rune-Catch-alls", "2026-08-04T14:07:42Z", 216),
}
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


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    url = f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}"
    for i in range(3):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "janea-bf/1.0"})
            with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i < 2:
                time.sleep(4); continue
            return {"__err": str(e)[:100]}
    return {}


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


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
ap.add_argument("--limit", type=int, default=0, help="cap total replays (0 = all)")
a = ap.parse_args()

rows = []
print("re-deriving the blind window from leads-statistics history[] type=SENT\n")
for cid, (label, since_s, expected) in BOUNDS.items():
    since = ts(since_s)
    skip, pages, found = 0, 0, 0
    while pages < 40:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            print(f"  {label}: ERROR {page['__err']}"); break
        pages += 1
        for row in (page.get("data") or []):
            for h in (row.get("history") or []):
                if str(h.get("type", "")).upper() != "SENT":
                    continue
                t = ts(h.get("time"))
                if not t or t < since:
                    continue
                found += 1
                rows.append({"campaign_id": cid, "campaign_name": label,
                             "lead_id": row.get("lead_id"), "to": row.get("to"),
                             "from": row.get("from"),
                             "map_id": row.get("email_lead_map_id"),
                             "seq": h.get("email_seq_number"),
                             "subject": h.get("subject"),
                             "stats_id": h.get("stats_id"),
                             "time": t.isoformat()})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.05)
    print(f"  {cid} {label:<18} pages={pages:<3} rows in span={found:<5} "
          f"auditor expected ~{expected}")

rows.sort(key=lambda r: r["time"])
print(f"\ntotal rows in the bounded blind window: {len(rows)}")
if a.limit:
    rows = rows[:a.limit]
    print(f"  --limit applied: replaying {len(rows)}")
by_camp = {}
for r in rows:
    by_camp[r["campaign_name"]] = by_camp.get(r["campaign_name"], 0) + 1
print(f"  per campaign: {by_camp}")
if rows:
    print(f"  span: {rows[0]['time']} .. {rows[-1]['time']}")

if not a.deploy:
    print("\n--deploy not given: nothing replayed.")
    print(f"  would POST {len(rows)} synthetic EMAIL_SENT events in batches of {BATCH} "
          f"with {PAUSE}s pauses (~{len(rows) // BATCH * PAUSE // 60} min)")
    sys.exit(0)

print(f"\nreplaying {len(rows)} events, batches of {BATCH}, {PAUSE}s pause "
      f"(OOM guard - a ~100-item burst killed this instance on 2026-07-30)\n")
sent, failed = 0, []
for i, r in enumerate(rows, 1):
    body = {"event_type": "EMAIL_SENT", "campaign_id": r["campaign_id"],
            "campaign_name": r["campaign_name"], "lead_id": r["lead_id"],
            "sl_email_lead_id": r["lead_id"], "sl_email_lead_map_id": r["map_id"],
            "app_url": (SL_INBOX + str(r["map_id"])) if r["map_id"] else None,
            "to_email": r["to"], "from_email": r["from"],
            "sequence_number": int(r["seq"]) if str(r["seq"] or "").isdigit() else 1,
            "timestamp": r["time"], "time_sent": r["time"], "event_timestamp": r["time"],
            "subject": r["subject"], "stats_id": r["stats_id"],
            "__reconciled": True, "__reconciled_by": "blind-window-backfill"}
    st = post(body)
    if st == 200:
        sent += 1
    else:
        failed.append({"row": r, "status": st})
    if i % BATCH == 0:
        print(f"  {i}/{len(rows)}  accepted={sent} failed={len(failed)}", flush=True)
        time.sleep(PAUSE)

print(f"\nreplayed: {sent}/{len(rows)}   failed: {len(failed)}")
for f in failed[:10]:
    print(f"   FAILED {f['status']}  {f['row']['to']} {f['row']['time']}")
json.dump({"at": datetime.now(timezone.utc).isoformat(), "bounds": BOUNDS,
           "total": len(rows), "sent": sent, "failed": failed, "per_campaign": by_camp},
          open(os.path.join(HERE, "wf1-release-evidence", "p05b_backfill.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/p05b_backfill.json")
sys.exit(0 if not failed else 1)
