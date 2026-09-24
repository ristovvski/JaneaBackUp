#!/usr/bin/env python3
"""W1.0.18 WIRE PROOF - watch the first wave hour's SENT executions.

The statics prove the bodies; only live SENT traffic proves the pagination. Pass condition, per Nik:
every SENT execution shows `__lead_candidates_read >= 1` and `__lead_read_errors: 0`.

Reads the n8n API ONLY - no Pipedrive calls. The auditor has Pipedrive priority until it reports,
and the wave's own traffic is sacred; a watcher must not compete with either.

RED conditions, any one of which is reported immediately rather than at the end:
  * __lead_candidates_read == 0        -> the read was not scoped, or the expression threw
  * __lead_read_errors > 0             -> a candidate we never read (429 or worse)
  * __leads_page_saturated == true     -> coverage shortfall
  * execution status != success
  * a lead CREATED while blind         -> the duplicate-factory signature we just closed

Writes JSON + a human log continuously, so a watcher that dies is visible as a stale file rather
than as silence (the C1 lesson: a monitor that died quietly is worse than no monitor).
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
OUT = os.path.join(HERE, "wf1-release-evidence", "w1018_wave_proof.json")
LOG = os.path.join(HERE, "wf1-release-evidence", "w1018_wave_proof.log")
# "Watch the first WAVE hour" is not the same as "watch for 75 minutes". The wave's start time is
# not reliably known - WF-2 only became the live receiver on 2026-08-10, so every earlier execution
# histogram is shadow-era traffic (08-04 peaks at 14Z, 08-10 at 21Z; neither is evidence). A fixed
# window pinned to a guessed 14:00Z would expire before the traffic and report "no traffic", which
# is not a pass. So: wait up to OUTER_MIN for the FIRST SENT execution, then watch for WAVE_MIN
# beyond it. The clock that matters starts when the wave does.
OUTER_MIN = int(os.environ.get("OUTER_MIN", "330"))
WAVE_MIN = int(os.environ.get("WAVE_MIN", "60"))
START = datetime.now(timezone.utc)
OUTER_DEADLINE = START + timedelta(minutes=OUTER_MIN)
DEADLINE = OUTER_DEADLINE
first_sent_at = None


def say(msg):
    line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        say(f"  n8n read failed (NOT an empty result): {str(e)[:120]}")
        return None


def node(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


say(f"=== W1.0.18 wave watch from {START.isoformat()} ===")
say(f"waiting up to {OUTER_MIN} min for the first SENT, then watching {WAVE_MIN} min past it")
say("pass = every SENT execution has __lead_candidates_read >= 1 and __lead_read_errors == 0")
seen, rows, reds = set(), [], []

while datetime.now(timezone.utc) < DEADLINE:
    ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
    for e in (ex or {}).get("data") or []:
        if e["id"] in seen:
            continue
        started = str(e.get("startedAt") or "")
        try:
            t = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except Exception:
            continue
        if t < START:
            seen.add(e["id"])
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        if det is None:
            continue                      # retry next cycle; do NOT mark seen
        seen.add(e["id"])
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        sel = next((s for s in ("Lead Select", "Lead Resolve", "B Lead Select", "U Lead Select")
                    if s in rd), None)
        if not sel:
            continue
        r = {
            "exec": e["id"], "at": started, "status": e.get("status"), "select": sel,
            "event": node(rd, "Normalize", "event"),
            "cands_read": node(rd, sel, "__lead_candidates_read"),
            "read_errors": node(rd, sel, "__lead_read_errors"),
            "saturated": node(rd, sel, "__leads_page_saturated"),
            "pages": node(rd, sel, "__lead_pages"),
            "rows": node(rd, sel, "__lead_rows"),
            "lead_id": node(rd, sel, "__lead_id"),
            "exists": node(rd, sel, "__lead_exists"),
            "adopted": node(rd, sel, "__person_adopted"),
            "created_lead": "Lead Create" in rd,
        }
        rows.append(r)
        bad = []
        if e.get("status") != "success":
            bad.append(f"status={e.get('status')}")
        if r["cands_read"] in (None, 0):
            bad.append(f"cands_read={r['cands_read']}")
        if r["read_errors"]:
            bad.append(f"read_errors={r['read_errors']}")
        if r["saturated"] is True:
            bad.append("SATURATED")
        if r["created_lead"] and (r["saturated"] is True or r["read_errors"]):
            bad.append("CREATED A LEAD WHILE BLIND")
        if r["event"] == "SENT" and first_sent_at is None:
            # the wave has started: from here the "first wave hour" clock is the one that counts
            first_sent_at = t
            DEADLINE = min(OUTER_DEADLINE, t + timedelta(minutes=WAVE_MIN))
            say(f"  >>> FIRST SENT at {t.isoformat()} - watching until {DEADLINE.isoformat()}")
        tag = "RED " if bad else "ok  "
        if bad:
            reds.append({**r, "why": bad})
        say(f"  [{tag}] exec {r['exec']} {r['event']} via {sel}: "
            f"cands_read={r['cands_read']} errors={r['read_errors']} "
            f"saturated={r['saturated']} rows={r['rows']} "
            f"lead={str(r['lead_id'])[:8]} created={r['created_lead']}"
            + (f"  <- {', '.join(bad)}" if bad else ""))
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"started": START.isoformat(), "rows": rows, "reds": reds,
                       "last_poll": datetime.now(timezone.utc).isoformat()},
                      f, indent=2, ensure_ascii=False, default=str)
    time.sleep(45)

sent = [r for r in rows if r["event"] == "SENT"]
say(f"\n=== WATCH COMPLETE ===")
say(f"executions reaching a lead read: {len(rows)}   of them SENT: {len(sent)}   REDs: {len(reds)}")
if first_sent_at is None:
    say("NO SENT TRAFFIC in the whole window - this is NOT a pass. The wave either did not run or "
        "did not reach WF-2; W1.0.18 stays statics-only, unproven on the wire.")
elif not rows:
    say("NO TRAFFIC OBSERVED - this is NOT a pass. W1.0.18 remains statics-only, unproven on the wire.")
elif reds:
    say("RED - see above; W1.0.18 is NOT wire-proven")
else:
    say("PASS - every observed execution scoped its read and read every candidate")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"started": START.isoformat(),
               "first_sent_at": first_sent_at.isoformat() if first_sent_at else None,
               "rows": rows, "reds": reds, "sent_count": len(sent),
               "verdict": ("no_sent_traffic" if first_sent_at is None
                           else ("red" if reds else "pass")),
               "finished": datetime.now(timezone.utc).isoformat()},
              f, indent=2, ensure_ascii=False, default=str)
sys.exit(1 if (reds or first_sent_at is None) else 0)
