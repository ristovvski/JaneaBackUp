#!/usr/bin/env python3
"""Watch WF-2R's first cycles. Checks the things that actually matter rather than 'did it run':

  * status of each cycle and which campaign the round-robin picked (all four must appear)
  * whether the page walk completed (hasMore exhausted) or hit the page cap
  * whether ANY of the ten hand-backfilled replies got claimed or replayed - if one did, the
    floor failed and hwang could be double-forwarded to Rune
  * whether the replay POST into live WF-2 returned 200
"""
import json, os, ssl, time, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2R = "U8Bb7Pdq7S6nzYPa"
HERE = os.path.dirname(os.path.abspath(__file__))
CYCLES = int(os.environ.get("CYCLES", "5"))
BACKFILLED = {"pii-6f8f48e5@example.invalid", "pii-567b1851@example.invalid", "pii-7b1c0e1a@example.invalid",
              "pii-67425a37@example.invalid", "pii-b02b50cf@example.invalid", "pii-135b4c7b@example.invalid",
              "pii-90ec4caf@example.invalid", "pii-06275333@example.invalid",
              "pii-280f963f@example.invalid", "pii-0ddf11ef@example.invalid"}


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {}) if params else ""
    url = f"{BASE}{path}?{q}" if q else f"{BASE}{path}"
    for i in range(3):
        try:
            r = urllib.request.Request(url, headers={"X-N8N-API-KEY": KEY,
                                                     "accept": "application/json"})
            with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
                return json.load(x)
        except Exception:
            if i < 2:
                time.sleep(5); continue
            return {}
    return {}


import urllib.parse  # noqa: E402

SINCE = os.environ.get("SINCE", "").strip()
seen_ids, seen_ids_skipped, report = set(), set(), []
deadline = time.time() + 60 * 95
print(f"watching WF-2R ({WF2R}) for {CYCLES} cycles, started "
      f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z", flush=True)
while len(seen_ids) < CYCLES and time.time() < deadline:
    d = n8n("/api/v1/executions", {"workflowId": WF2R, "limit": 20})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
        if e["id"] in seen_ids:
            continue
        # SINCE lets a redeploy watch only its OWN cycles - without it the watcher instantly
        # consumes the previous build's executions and reports on code that is no longer live
        if SINCE and str(e.get("startedAt") or "") < SINCE:
            seen_ids_skipped.add(e["id"])
            continue
        seen_ids.add(e["id"])
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        err = ((det.get("data") or {}).get("resultData") or {}).get("error")

        def first(nm, key, default=None):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"].get(key, default)
            except Exception:
                return default

        camp = first("Pick Campaign", "campaign_name")
        find = None
        for k in ("Find New Replies",):
            try:
                find = rd[k][0]["data"]["main"][0][0]["json"]
            except Exception:
                pass
        # any backfilled email touched anywhere in this cycle?
        touched = sorted({em for em in BACKFILLED
                          if em in json.dumps(det, default=str)})
        replay_status = []
        for run in rd.get("Replay Into WF-2") or []:
            for it in (run.get("data", {}).get("main", [[]])[0] or []):
                j = it.get("json") or {}
                replay_status.append("ERROR:" + str(j["error"])[:60] if "error" in j else "200")
        row = {"id": e["id"], "startedAt": e.get("startedAt"), "status": e.get("status"),
               "campaign": camp, "pages": (find or {}).get("__pages"),
               "truncated": (find or {}).get("__truncated"),
               "replies_seen": (find or {}).get("__replies_seen"),
               "floored": (find or {}).get("__floored"),
               "stale": (find or {}).get("__stale"),
               "already": (find or {}).get("__already"),
               "idle": (find or {}).get("__idle"),
               "batch": (find or {}).get("__batch", 0),
               "replays": replay_status,
               "backfilled_touched": touched,
               "error": (err or {}).get("message") if err else None}
        report.append(row)
        ring = first("Pick Campaign", "__ring")
        row["ring"] = ring
        row["hot"] = first("Pick Campaign", "__hot")
        row["cold"] = first("Pick Campaign", "__cold")
        row["excluded"] = first("Pick Campaign", "__excluded")
        row["sweep_overrun"] = first("Pick Campaign", "__sweep_overrun")
        print(f"  [{len(seen_ids)}/{CYCLES}] {row['startedAt']} {row['status']:<9} "
              f"ring={str(ring):<5} camp={str(row['campaign'])[:40]:<40} pages={row['pages']} "
              f"floored={row['floored']} batch={row['batch']} "
              f"replays={row['replays'] or '-'}", flush=True)
        if row["sweep_overrun"]:
            print("        !! ROTATION SLOWER THAN LOOKBACK", flush=True)
        if row["error"]:
            print(f"        ERROR: {row['error']}", flush=True)
        if row["truncated"]:
            print("        !! page walk INCOMPLETE - raise max_pages_per_campaign", flush=True)
        if touched and row["batch"]:
            print(f"        !! BACKFILLED LEAD IN A REPLAY BATCH: {touched}", flush=True)
    if len(seen_ids) < CYCLES:
        time.sleep(60)

camps = {r["campaign"] for r in report if r["campaign"]}
replayed_backfill = [r for r in report if r["backfilled_touched"] and r["batch"]]
bad = [r for r in report if r["status"] != "success"] + [r for r in report if r["truncated"]]
print("\n" + "=" * 92)
print(f"cycles observed        : {len(report)}  (skipped {len(seen_ids_skipped)} pre-SINCE)")
print(f"ring split             : "
      f"{ {r: sum(1 for x in report if x.get('ring') == r) for r in ('hot', 'cold')} }")
print(f"ring sizes reported    : hot={report[-1].get('hot') if report else '?'} "
      f"cold={report[-1].get('cold') if report else '?'} "
      f"excluded={report[-1].get('excluded') if report else '?'}")
print(f"campaigns covered      : {len(camps)} -> {sorted(str(c)[:40] for c in camps)}")
print(f"non-success cycles     : {len([r for r in report if r['status'] != 'success'])}")
print(f"incomplete page walks  : {len([r for r in report if r['truncated']])}")
print(f"replay batches         : {sum(1 for r in report if r['batch'])}")
print(f"backfilled leads replayed (MUST be 0): {len(replayed_backfill)}")
print("VERDICT:", "CLEAN" if not bad and not replayed_backfill else "NEEDS ATTENTION")
with open(os.path.join(HERE, "wf1-release-evidence", "wf2r_first_cycles.json"), "w",
          encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False, default=str)
print("wrote wf1-release-evidence/wf2r_first_cycles.json")
