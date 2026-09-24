#!/usr/bin/env python3
"""REPAIR - Person-8768306e, the one false reply in the retained window. Dry-run by default.

Four corrections, each reversible, each verified by reading the record back:

  1. tombstone registry row **33166** via `dnc_s4_retirement_removal` with
     `removed_reason: false_reply_empty_body` (the path only learned to carry a caller-supplied
     reason today - it hardcoded 'rule_change_2026-08-26_melisa' until version 50a7f964)
  2. strip `3. Responded` from lead 987d0600 - `1. Cold` and `2. Connected` stay
  3. close handover task 46416
  4. LEAVE reply activity 46415 in place, prefixing its note so the timeline explains itself.
     CRM history is not ours to delete; an unexplained Responded that came and went is worse than
     a corrected record.

Everything the script touches is captured BEFORE the write into
`heath_repair_baseline.json`, so a rollback is a replay.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HOST = BASE.split("/api/")[0].rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))

ROW_ID = 33166
LEAD = "987d0600-ac44-11f1-926c-6949d156b78a"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
TASK = 46416
ACTIVITY = 46415
PREFIX = "[false reply — empty accept artefact] "

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
a = ap.parse_args()
MODE = "LIVE" if a.live else "DRY RUN"


def pd(p, method="GET", body=None, att=0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + p, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and att < 4:
            time.sleep(4)
            return pd(p, method, body, att + 1)
        return {"__err": "HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace"))}
    except Exception as e:
        return {"__err": str(e)[:140]}


print("=" * 72)
print("MODE: %s" % MODE)
print("=" * 72)

# ---------------------------------------------------------------- baseline
lead = (pd("/v1/leads/%s" % LEAD) or {}).get("data") or {}
task = (pd("/api/v2/activities/%d" % TASK) or {}).get("data") or {}
act = (pd("/api/v2/activities/%d" % ACTIVITY) or {}).get("data") or {}
labels = {x["id"]: x["name"] for x in ((pd("/v1/leadLabels") or {}).get("data") or [])}
before = {"lead_label_ids": lead.get("label_ids"), "task_done": task.get("done"),
          "activity_note": act.get("note"), "registry_row": ROW_ID}

# RE-APPLY GUARD. This runs a second time, after a revert. Refuse unless the CRM is actually back at
# the state the original baseline recorded - otherwise the "rollback" file would be overwritten with
# some in-between state and the real prior values lost.
_bp = os.path.join(HERE, "heath_repair_baseline.json")
if os.path.exists(_bp):
    _old = json.load(open(_bp, encoding="utf-8"))
    if sorted(_old.get("lead_label_ids") or []) != sorted(lead.get("label_ids") or []):
        sys.exit("current labels %s do not match the recorded baseline %s - refusing to overwrite "
                 "the rollback file" % (lead.get("label_ids"), _old.get("lead_label_ids")))
    print("re-apply guard: current state matches the recorded baseline")
with open(_bp, "w", encoding="utf-8") as f:
    json.dump(before, f, ensure_ascii=False, indent=1)
print("baseline -> heath_repair_baseline.json")
print("  lead labels : %s" % [labels.get(x, x) for x in (lead.get("label_ids") or [])])
print("  task %d done: %r  subject=%r" % (TASK, task.get("done"), str(task.get("subject"))[:48]))
print("  activity %d note length: %d" % (ACTIVITY, len(str(act.get("note") or ""))))

if not lead:
    sys.exit("lead not readable - aborting")
cur = list(lead.get("label_ids") or [])
if RESPONDED not in cur:
    print("\n  NOTE: `3. Responded` is not on the lead - step 2 is already satisfied")
want = [x for x in cur if x != RESPONDED]
print("\nplanned label change: %s -> %s"
      % ([labels.get(x, x) for x in cur], [labels.get(x, x) for x in want]))

note = str(act.get("note") or "")
already = note.startswith("[false reply")
print("planned note prefix : %s" % ("ALREADY PRESENT, skipping" if already else PREFIX.strip()))

# ---------------------------------------------------------------- 1. registry tombstone
print("\n--- 1. registry row %d ---" % ROW_ID)
payload = {"row_ids": [ROW_ID], "dry_run": not a.live,
           "removed_reason": "false_reply_empty_body"}
req = urllib.request.Request(HOST + "/webhook/{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}", method="POST",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=120, context=ctx) as x:
        res = json.loads(x.read())
except Exception as e:
    res = {"__err": str(e)[:200]}
print("  payload: %s" % json.dumps(payload))
print("  result : %s" % json.dumps(res, ensure_ascii=False)[:300])
if a.live and res.get("dry_run") is not False:
    sys.exit("removal did not run in write mode - ABORT before touching Pipedrive")

# ---------------------------------------------------------------- 2. strip the label
print("\n--- 2. lead labels ---")
if not a.live:
    print("  would PATCH /v1/leads/%s label_ids=%s" % (LEAD, want))
elif RESPONDED not in cur:
    print("  nothing to do")
else:
    r = pd("/v1/leads/%s" % LEAD, "PATCH", {"label_ids": want})
    print("  -> %s" % json.dumps(r, ensure_ascii=False)[:180])

# ---------------------------------------------------------------- 3. close the task
print("\n--- 3. handover task %d ---" % TASK)
if not a.live:
    print("  would PATCH /api/v2/activities/%d done=true" % TASK)
elif task.get("done"):
    print("  already done")
else:
    r = pd("/api/v2/activities/%d" % TASK, "PATCH", {"done": True})
    print("  -> %s" % json.dumps(r, ensure_ascii=False)[:180])

# ---------------------------------------------------------------- 4. annotate the activity
print("\n--- 4. reply activity %d (kept, annotated) ---" % ACTIVITY)
if already:
    print("  prefix already present")
elif not a.live:
    print("  would PATCH note = PREFIX + existing (%d chars)" % len(note))
else:
    r = pd("/api/v2/activities/%d" % ACTIVITY, "PATCH", {"note": PREFIX + note})
    print("  -> %s" % json.dumps(r, ensure_ascii=False)[:180])

if not a.live:
    print("\nDRY RUN - nothing written. Re-run with --live.")
    sys.exit(0)

# ---------------------------------------------------------------- verify
print("\n" + "=" * 72)
print("VERIFY - reading every record back")
print("=" * 72)
time.sleep(2)
lead2 = (pd("/v1/leads/%s" % LEAD) or {}).get("data") or {}
task2 = (pd("/api/v2/activities/%d" % TASK) or {}).get("data") or {}
act2 = (pd("/api/v2/activities/%d" % ACTIVITY) or {}).get("data") or {}
now_labels = [labels.get(x, x) for x in (lead2.get("label_ids") or [])]
checks = [
    ("`3. Responded` removed", RESPONDED not in (lead2.get("label_ids") or [])),
    ("`1. Cold` kept", "1. Cold" in now_labels),
    ("`2. Connected` kept", "2. Connected" in now_labels),
    ("handover task closed", task2.get("done") is True),
    ("reply activity still exists", bool(act2.get("id"))),
    ("reply activity annotated", str(act2.get("note") or "").startswith("[false reply")),
    ("registry removal ran in write mode", res.get("dry_run") is False),
    ("registry removal processed 1 row", res.get("processed") == 1),
]
allok = True
for label, good in checks:
    print("  [%s] %s" % ("ok " if good else "FAIL", label))
    allok = allok and good
print("\n  lead labels now: %s" % now_labels)
print("\n=== %s ===" % ("REPAIR CLEAN" if allok else "REPAIR HAS PROBLEMS"))
sys.exit(0 if allok else 1)
