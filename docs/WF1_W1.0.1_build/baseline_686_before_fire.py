#!/usr/bin/env python3
"""PRE-WRITE BASELINE for FIRE_PIPEDRIVE window 1. READ ONLY against Pipedrive.

Captures the CURRENT value of person field `9c018b74…` (DNC Status) for all **580** pending person
ids - not just the 250 the dev run happened to chunk. Reason: the DNC reply capture went live today
and writes new pending rows on every campaign reply (amity.curry got one at 12:58Z), so the live
run's first-250 slice can differ from the dev run's. Baselining the whole pending set means the
rollback and the post-verify cannot be defeated by the set moving between runs.

Rollback from this file is a replay: PATCH each person back to the value recorded here.
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
FIELD = "9c018b7406ebc481b9c108a487f76c4d09f91c9b"
ACTIVE = 686


def pd(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and a < 5:
            time.sleep(3 + a * 3)
            return pd(p, a + 1)
        return {"__err": "HTTP %s" % e.code}
    except Exception as e:
        if a < 4:
            time.sleep(3)
            return pd(p, a + 1)
        return {"__err": str(e)[:120]}


ids = json.load(open(os.path.join(HERE, "fire_target_ids_48563.json"), encoding="utf-8"))
pending = [int(i) for i in ids["pending_ids"]]
chunk = [int(i) for i in ids["chunk_ids"]]
print("baselining %d pending person ids (chunk-1 target: %d)" % (len(pending), len(chunk)))

rows, errs = {}, {}
for n, pid in enumerate(pending, 1):
    # `include_fields=custom_fields` is a 400 on this endpoint ("One or more of the given values is
    # invalid") - the plain read already returns custom_fields as a dict. All 580 baseline reads
    # failed this way on the first attempt; a baseline of zero rows would have meant firing with no
    # rollback, which is why it is asserted below rather than assumed.
    r = pd("/api/v2/persons/%d" % pid)
    if r.get("__err") or not r.get("data"):
        errs[pid] = r.get("__err") or "no data"
        continue
    cf = (r["data"].get("custom_fields") or {})
    val = cf.get(FIELD)
    rows[pid] = {"dnc_status_raw": val,
                 "is_686": (val == ACTIVE) or (isinstance(val, dict) and val.get("id") == ACTIVE)
                 or (isinstance(val, list) and ACTIVE in val),
                 "name": r["data"].get("name")}
    if n % 100 == 0:
        print("  %d/%d read" % (n, len(pending)), flush=True)
    time.sleep(0.03)          # 80 req / 2 s is the ceiling; this sits far under it

already = sum(1 for v in rows.values() if v["is_686"])
print("\nread ok        : %d" % len(rows))
print("read errors    : %d %s" % (len(errs), list(errs.items())[:4]))
print("already 686    : %d   <-- these should be no-ops for the projection" % already)
print("not yet 686    : %d" % (len(rows) - already))
inchunk = [p for p in chunk if p in rows]
print("chunk-1 rows baselined: %d of %d   already 686 within chunk: %d" % (
    len(inchunk), len(chunk), sum(1 for p in inchunk if rows[p]["is_686"])))

out = os.path.join(HERE, "baseline_686_before_window1.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"field": FIELD, "active_option": ACTIVE,
               "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "pending_ids": pending, "chunk1_ids": chunk,
               "already_686": already, "read_errors": errs, "rows": rows}, f,
              ensure_ascii=False, indent=1)
print("\n-> %s" % os.path.basename(out))

# --- the assertion that makes this file trustworthy: a baseline is worthless if it is empty
if len(rows) < len(pending):
    print("\nINCOMPLETE BASELINE: %d of %d read. DO NOT FIRE - rollback would be partial."
          % (len(rows), len(pending)))
    sys.exit(1)
print("\nBASELINE COMPLETE: %d/%d persons captured, rollback is a replay of this file." %
      (len(rows), len(pending)))
