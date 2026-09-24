#!/usr/bin/env python3
"""Close the Handover activities Pipedrive auto-created when R1 applied '3. Responded'.

These are identified NOT by guessing but by three conjoined facts: type == 'handover',
still open, and add_time on 2026-08-06 (the backfill ran 13:22Z). Pre-existing open activities
on the same leads - e.g. hwang's 2026-07-21 'Follow up on this lead!' - are deliberately left
untouched; they are not ours to close.
"""
import json, os, ssl, urllib.error, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
DRY = os.environ.get("DRY_RUN", "1") != "0"
NOTE = ("Closed by historical backfill. This Handover was auto-created when the '3. Responded' "
        "label was applied while recovering a reply that arrived during the 2026-08-04/05 WF-2 "
        "outage and was never processed at the time. The reply itself is recorded on this lead "
        "as a done 'Email reply' activity containing the full text. No action is needed here.")


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    try:
        r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                                   headers={"x-api-token": PDT, "User-Agent": "janea-r1/1.0",
                                            "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:300]}


with open(os.path.join(HERE, "wf1-release-evidence", "r1_reply_backfill_live.json"),
          encoding="utf-8") as f:
    run = json.load(f)

targets, seen = [], set()
for s in run["plan"]:
    lid = s.get("lead_id")
    if not lid or lid in seen:
        continue
    seen.add(lid)
    for a in ((pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []):
        if a.get("done"):
            continue
        if str(a.get("type")) != "handover":
            print(f"  skip (not a handover): {a['id']} {a.get('subject')!r} "
                  f"add_time={a.get('add_time')} on {s['email']}")
            continue
        if not str(a.get("add_time") or "").startswith("2026-08-06"):
            print(f"  skip (pre-existing): {a['id']} {a.get('subject')!r} "
                  f"add_time={a.get('add_time')} on {s['email']}")
            continue
        targets.append({"id": a["id"], "email": s["email"], "lead_id": lid,
                        "subject": a.get("subject"), "add_time": a.get("add_time")})

print(f"\nauto-created Handovers to close: {len(targets)}  "
      f"({'DRY-RUN' if DRY else 'LIVE'})")
closed = []
for t in targets:
    print(f"  {t['id']}  {t['email']:<34} {t['subject']!r}  {t['add_time']}")
    if not DRY:
        r = pd(f"/api/v2/activities/{t['id']}", "PATCH", {"done": True, "note": NOTE})
        ok = bool((r or {}).get("data"))
        print(f"      -> {'closed' if ok else 'FAILED ' + json.dumps(r)[:250]}")
        if ok:
            closed.append(t)

if not DRY:
    print(f"\nclosed: {len(closed)}/{len(targets)}")
    print("\nre-reading to confirm:")
    still = 0
    for lid in seen:
        for a in ((pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []):
            if not a.get("done") and str(a.get("type")) == "handover" \
                    and str(a.get("add_time") or "").startswith("2026-08-06"):
                still += 1
                print(f"  STILL OPEN: {a['id']} on lead {lid}")
    print(f"  backfill-created Handovers still open: {still}")

with open(os.path.join(HERE, "wf1-release-evidence", "r1_handovers.json"), "w",
          encoding="utf-8") as f:
    json.dump({"dry_run": DRY, "targets": targets, "closed": closed}, f, indent=2,
              ensure_ascii=False)
