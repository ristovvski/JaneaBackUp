#!/usr/bin/env python3
"""POST-VERIFY for FIRE_PIPEDRIVE window 1. READ ONLY.

Four assertions, in the order that matters:

  1. PER-RECORD READ-BACK, the primary. For every person the run wrote, read field `9c018b74…`
     from Pipedrive and assert it is option 686. Deterministic and immune to other writers - which a
     population delta is not, on a field four Zaps have written to before.
  2. NOTHING ELSE MOVED. The 330 pending persons this window did NOT target must still be un-686.
     This is the "and no others" half, and it is the one a delta count cannot give you.
  3. LABEL UNION PRESERVED on the leads that got the DNC label. The pre-write label set is
     recoverable from the execution itself: `PD Label Union` emitted the union, so
     existing = union - {dnc}. Assert the live lead still carries every one of those, plus dnc.
  4. REGISTRY CLAIM matches the CRM: the count marked done equals the count that actually reads
     back as 686. A row marked done whose person is not 686 is the failure this estate keeps
     finding - a write that reported success and achieved nothing.

Usage: verify_window1.py <execution_id>
"""
import json
import os
import ssl
import sys
import time
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
KEY = os.environ["N8N_API_KEY"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
FIELD = "9c018b7406ebc481b9c108a487f76c4d09f91c9b"
ACTIVE = 686
DNC_LABEL = "52a7c290-fc73-11f0-ad98-81d4703453f3"
EXEC = sys.argv[1] if len(sys.argv) > 1 else None
if not EXEC:
    sys.exit("usage: verify_window1.py <execution_id>")


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


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def is686(val):
    return (val == ACTIVE) or (isinstance(val, dict) and val.get("id") == ACTIVE) \
        or (isinstance(val, list) and ACTIVE in val)


bl = json.load(open(os.path.join(HERE, "baseline_686_before_window1.json"), encoding="utf-8"))
run = (((n8n("/api/v1/executions/%s?includeData=true" % EXEC) or {}).get("data") or {})
       .get("resultData") or {}).get("runData") or {}


def items(nm):
    try:
        return [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
    except Exception:
        return []


targeted = [int(r["pipedrive_person_id"]) for r in items("PD Limit Chunk")
            if r.get("pipedrive_person_id")]
marked = len(items("PD Mark Done (with lead)")) + len(items("PD Mark Done (no lead)"))
werrs = items("PD Mark Write Error")
print("execution %s: targeted=%d  marked_done=%d  marked_write_error=%d"
      % (EXEC, len(targeted), marked, len(werrs)))

# ---- 1. per-record read-back
print("\n--- 1. per-record read-back of the targeted persons ---")
good, bad = [], []
for n, pid in enumerate(targeted, 1):
    r = pd("/api/v2/persons/%d" % pid)
    val = ((r.get("data") or {}).get("custom_fields") or {}).get(FIELD)
    (good if is686(val) else bad).append((pid, val))
    if n % 100 == 0:
        print("  %d/%d" % (n, len(targeted)), flush=True)
    time.sleep(0.03)
print("  686 confirmed : %d / %d" % (len(good), len(targeted)))
print("  NOT 686       : %d %s" % (len(bad), bad[:6]))

# ---- 2. nothing else moved
untargeted = [p for p in (int(i) for i in bl["pending_ids"]) if p not in set(targeted)]
print("\n--- 2. the %d pending persons this window did NOT target ---" % len(untargeted))
moved = []
for n, pid in enumerate(untargeted, 1):
    r = pd("/api/v2/persons/%d" % pid)
    val = ((r.get("data") or {}).get("custom_fields") or {}).get(FIELD)
    if is686(val):
        moved.append(pid)
    time.sleep(0.03)
print("  unexpectedly 686: %d %s" % (len(moved), moved[:8]))

# ---- 3. label union preserved
print("\n--- 3. label union on the leads that were patched ---")
unions = {r.get("lead_id"): (r.get("label_ids") or []) for r in items("PD Label Union")
          if r.get("lead_id")}
print("  leads the run built a union for: %d" % len(unions))
lab_ok, lab_bad = 0, []
for n, (lid, union) in enumerate(unions.items(), 1):
    expected_existing = [x for x in union if x != DNC_LABEL]
    r = pd("/v1/leads/%s" % lid)
    live = ((r.get("data") or {}).get("label_ids")) or []
    if DNC_LABEL in live and all(x in live for x in expected_existing):
        lab_ok += 1
    else:
        lab_bad.append({"lead": lid, "expected_at_least": expected_existing + [DNC_LABEL],
                        "live": live})
    if n % 75 == 0:
        print("  %d/%d" % (n, len(unions)), flush=True)
    time.sleep(0.03)
print("  union preserved + dnc present: %d / %d" % (lab_ok, len(unions)))
print("  problems: %d" % len(lab_bad))
for p in lab_bad[:4]:
    print("     %s" % json.dumps(p, ensure_ascii=False)[:260])

# ---- 4. registry claim vs CRM truth
print("\n--- 4. registry claim vs CRM truth ---")
print("  rows marked done      : %d" % marked)
print("  persons reading as 686: %d" % len(good))
verdict = (len(bad) == 0 and len(moved) == 0 and not lab_bad and marked == len(good))
print("  match: %s" % ("YES" if marked == len(good) else
                        "NO - a row claims done for a person that is not 686"))

print("\n=================== VERDICT: %s ===================" % ("CLEAN" if verdict else "PROBLEMS"))
out = os.path.join(HERE, "window1_verify_%s.json" % EXEC)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"exec": EXEC, "targeted": len(targeted), "confirmed_686": len(good),
               "not_686": bad, "untargeted_checked": len(untargeted),
               "untargeted_moved": moved, "leads_checked": len(unions),
               "label_ok": lab_ok, "label_problems": lab_bad,
               "marked_done": marked, "write_errors": len(werrs), "verdict": verdict}, f,
              ensure_ascii=False, indent=1)
print("-> %s" % os.path.basename(out))
sys.exit(0 if verdict else 1)
