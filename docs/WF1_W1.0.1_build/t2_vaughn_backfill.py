#!/usr/bin/env python3
"""T1 item 2 - backfill Person-0ee7dfb2's lost LinkedIn reply (R1 pattern).

WHY HE WAS MISSED: HeyReach emits two webhook events per reply. Only the non-actionable
`message_reply_received` arrived (exec 14302 -> NoOp); the actionable
`every_message_reply_received` never did, so nothing was written.

Writes, matching WF-1's own M7 contract:
  * lead labels: UNION with '3. Responded' (cumulative, never removes)
  * a done 'LinkedIn reply' activity on /api/v2/activities carrying the message text

NOTE ON THE ACTIVE WIPER INCIDENT: a live automation has been reverting '3. Responded' on some
leads seconds after we write it. This backfill therefore RE-READS the label ~90s after writing and
reports whether it survived. If it is reverted, that is not a failed backfill - it is a live
observation that the wiper is still running, and it goes in the incident record.

DRY_RUN=1 default.
"""
import json, os, ssl, time, urllib.error, urllib.request
from datetime import datetime, timezone

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
DRY = os.environ.get("DRY_RUN", "1") != "0"
HERE = os.path.dirname(os.path.abspath(__file__))

PERSON = 84857
OWNER = 16340280
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NAMES = {"a6d359b0-6a45-11ed-ab46-5b95b19fcb18": "1. Cold",
         "ca698a50-bdfb-11ef-8172-510383583b0e": "2. Connected",
         "c9d4b550-bcf3-11ef-a843-357f91e826ec": "3. Responded"}
REPLY_TIME = "2026-08-08T02:42:07Z"
REPLY_TEXT = "Sorry i missed most of the conference. I'm not in need of SW dev services."
PROFILE = "https://www.linkedin.com/in/pii-bf2efff7"


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea-t1-backfill/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:300]}


leads = (pd(f"/v1/leads?limit=50&person_id={PERSON}&archived_status=all") or {}).get("data") or []
if len(leads) != 1:
    print(f"REFUSING: expected exactly 1 lead for person {PERSON}, found {len(leads)}")
    for L in leads:
        print("  ", L.get("id"), L.get("title"))
    raise SystemExit(2)
lead = leads[0]
lead_id = lead["id"]
campaign = lead.get("1cd81dfcac8a5583935ff4b60e284d0e580db0b6") or ""
title = lead.get("title") or ""
if not campaign:
    # Make-created leads leave the campaign field empty; fall back to the title convention
    campaign = title.split(" - ", 1)[1].rsplit(" - ", 1)[0] if " - " in title else title
existing = list(lead.get("label_ids") or [])
print(f"lead    : {lead_id}")
print(f"title   : {title}")
print(f"campaign: {campaign}")
print(f"labels  : {[NAMES.get(x, x) for x in existing]}")

union = existing[:]
if RESPONDED not in union:
    union.append(RESPONDED)
label_body = {"label_ids": union}
act_body = {
    "subject": f"LinkedIn reply — {campaign}",
    "type": "email", "done": True, "owner_id": OWNER, "lead_id": lead_id,
    "due_date": REPLY_TIME[:10],
    "note": (f"{REPLY_TEXT}\n\n— {PROFILE}\n"
             f"— historical backfill: this reply arrived {REPLY_TIME} but HeyReach delivered only "
             f"the non-actionable event copy, so WF-1 never processed it "
             f"(execution 14302 took the NoOp branch)."),
}

print(f"\n{'DRY-RUN' if DRY else 'LIVE'}")
print(f"  [A] PATCH /v1/leads/{lead_id}  ->  {[NAMES.get(x, x) for x in union]}"
      + ("  (no change needed)" if union == existing else ""))
print(f"  [B] POST /api/v2/activities   ->  {act_body['subject']!r}, note {len(act_body['note'])} chars")

if DRY:
    raise SystemExit(0)

results = {}
if union != existing:
    r = pd(f"/v1/leads/{lead_id}", "PATCH", label_body)
    ok = bool((r or {}).get("data"))
    results["label"] = "ok" if ok else json.dumps(r)[:250]
    print(f"      -> label patch {'ok' if ok else 'FAILED ' + results['label']}")
else:
    results["label"] = "skipped (already present)"

r = pd("/api/v2/activities", "POST", act_body)
aid = ((r or {}).get("data") or {}).get("id")
results["activity"] = aid or json.dumps(r)[:250]
print(f"      -> activity {aid if aid else 'FAILED ' + str(results['activity'])}")

# wiper observation - re-read after the window in which the clobber has been seen (7s and 37s)
print("\nwaiting 90s to see whether '3. Responded' survives (active wiper incident)...")
time.sleep(90)
after = (pd(f"/v1/leads/{lead_id}") or {}).get("data") or {}
now_labels = after.get("label_ids") or []
survived = RESPONDED in now_labels
print(f"  labels now  : {[NAMES.get(x, x) for x in now_labels]}")
print(f"  update_time : {after.get('update_time')}")
print(f"  RESPONDED SURVIVED: {survived}")
if not survived:
    print("  *** WIPED AGAIN - the wiper is STILL LIVE. This is a fresh, dated data point for "
          "the incident, not a backfill failure. ***")
results["responded_survived"] = survived
results["labels_after"] = now_labels
results["update_time_after"] = after.get("update_time")

with open(os.path.join(HERE, "wf1-release-evidence", "t2_vaughn_backfill.json"), "w",
          encoding="utf-8") as f:
    json.dump({"lead_id": lead_id, "person_id": PERSON, "campaign": campaign,
               "reply_time": REPLY_TIME, "results": results,
               "ran_at": datetime.now(timezone.utc).isoformat()}, f, indent=2,
              ensure_ascii=False)
print("\nwrote wf1-release-evidence/t2_vaughn_backfill.json")
