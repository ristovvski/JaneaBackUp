#!/usr/bin/env python3
"""B4 pass 2 - graded re-smoke with Make OFF and the CRM fixture in place.

COUNTER FIX (the bug that would have passed a double-forward): pass 1 counted forwards from a
WF-2 execution list captured BEFORE the reply arrived, so the relevant execution was not in it and
it reported 0 while the wire carried 2. Two corrections:
  * the execution list is re-fetched at count time, never reused
  * the AUTHORITY is Smartlead's own message history (type == 'FORWARD' after the reply), because
    our executions only prove what WE did, never what the wire carried. Our executions are still
    counted, as a cross-check, and a disagreement is reported rather than resolved silently.

Graded criteria: exactly ONE forward · category · exactly one alert · label patch · reply activity
· '3. Responded' on the lead · Handover fires.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
CID, SL_LEAD = 3686187, "4306240392"
EMAIL = "pii-c61c7d08@example.invalid"
PD_LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
SINCE = os.environ.get("SINCE", "2026-08-10T12:46:00Z")
WINDOW = int(os.environ.get("WINDOW_MIN", "30"))
DEADLINE = datetime.now(timezone.utc) + timedelta(minutes=WINDOW)


def _get(url, headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                {"User-Agent": "janea-b4b/1.0"})


def pd(p):
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea-b4b/1.0"})


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


print(f"B4 pass 2 - waiting for a reply after {SINCE} (window {WINDOW} min)", flush=True)

reply = None
while datetime.now(timezone.utc) < DEADLINE and not reply:
    h = (sl(f"/campaigns/{CID}/leads/{SL_LEAD}/message-history") or {}).get("history") or []
    reps = [m for m in h if str(m.get("type", "")).upper() == "REPLY"
            and str(m.get("time", "")) > SINCE]
    if reps:
        reply = reps[-1]
        break
    time.sleep(30)

if not reply:
    print("no new reply inside the window", flush=True)
    sys.exit(2)

rt = str(reply.get("time"))
print(f"\nREPLY at {rt}: {str(reply.get('email_body'))[:100]!r}", flush=True)
time.sleep(75)          # let WF-2 process and Smartlead record the forward

# ---------- AUTHORITY: Smartlead's own history
hist = (sl(f"/campaigns/{CID}/leads/{SL_LEAD}/message-history") or {}).get("history") or []
fwd_wire = [m for m in hist if str(m.get("type", "")).upper() == "FORWARD"
            and str(m.get("time", "")) > rt]
print(f"\n[WIRE] Smartlead FORWARD entries after this reply: {len(fwd_wire)}", flush=True)
for m in fwd_wire:
    print(f"    {m.get('time')}  -> {m.get('to')}", flush=True)

# ---------- CROSS-CHECK: our own executions, list re-fetched NOW
d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 40})
ours, our_fwd = [], 0
for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
    if str(e.get("startedAt") or "") < rt:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    lead = g(rd, "Normalize", "lead") or {}
    if str(lead.get("email", "")).lower() != EMAIL:
        continue
    row = {"id": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
           "event": g(rd, "Normalize", "event"),
           "reconciled_by": g(rd, "Normalize", "__reconciled_by"),
           "duplicate": g(rd, "Dedupe", "__duplicate"),
           "category": g(rd, "Classify Parse", "__category"),
           "confidence": g(rd, "Classify Parse", "__confidence"),
           "forward_to": g(rd, "Forward Resolve", "__forward_to"),
           "forward_owner": g(rd, "Forward Resolve", "__forward_owner"),
           "forward_ran": bool(rd.get("SL Forward Email")),
           "lead_id": g(rd, "Lead Resolve", "__lead_id"),
           "label_patch": bool(rd.get("Lead Labels Union")),
           "activity": bool(rd.get("Reply Activity")),
           "alert": bool(rd.get("Reply Alert")),
           "write_mode": g(rd, "CONFIG", "WRITE_MODE")}
    ours.append(row)
    if row["forward_ran"]:
        our_fwd += 1
print(f"\n[OURS] WF-2 executions for this lead since the reply: {len(ours)}", flush=True)
for r in ours:
    print(f"    {r['at']} id={r['id']} event={r['event']} by={r['reconciled_by']} "
          f"dup={r['duplicate']} fwd={r['forward_ran']} lead={str(r['lead_id'])[:8]} "
          f"label={r['label_patch']} act={r['activity']} alert={r['alert']}", flush=True)

# ---------- CRM state
L = (pd(f"/v1/leads/{PD_LEAD}") or {}).get("data") or {}
acts = (pd(f"/api/v2/activities?lead_id={PD_LEAD}&limit=50") or {}).get("data") or []
replies_act = [a for a in acts if "reply" in str(a.get("subject", "")).lower()]
handovers = [a for a in acts if str(a.get("type")) == "handover"]

first = ours[0] if ours else {}
checks = {
    "exactly ONE forward on the wire": len(fwd_wire) == 1,
    "our executions agree with the wire": our_fwd == len(fwd_wire),
    "categorized": bool(first.get("category")),
    "forward to correct owner": first.get("forward_to") == "rune@janeasystems.com",
    "exactly one alert": sum(1 for r in ours if r["alert"]) == 1,
    "lead resolved": bool(first.get("lead_id")),
    "label patch ran": any(r["label_patch"] for r in ours),
    "'3. Responded' on lead": RESPONDED in (L.get("label_ids") or []),
    "reply activity written": len(replies_act) >= 1,
    "Handover fired": len(handovers) >= 1,
    "WRITE_MODE live": first.get("write_mode") == "live",
}
print("\n--- B4 PASS 2 GRADED ---", flush=True)
for k, v in checks.items():
    print(f"  [{'OK ' if v else 'RED'}] {k}", flush=True)
print(f"\n  category={first.get('category')!r} conf={first.get('confidence')} "
      f"-> {first.get('forward_to')} ({first.get('forward_owner')})", flush=True)
print(f"  lead labels now: {L.get('label_ids')}", flush=True)
print(f"  activities: {len(acts)} (reply-ish {len(replies_act)}, handover {len(handovers)})",
      flush=True)
if our_fwd != len(fwd_wire):
    print(f"\n  !! DISAGREEMENT: wire says {len(fwd_wire)} forward(s), our executions say "
          f"{our_fwd}. The wire is authoritative; investigate before trusting either.", flush=True)

ok = all(checks.values())
print(f"\nB4 PASS 2: {'GREEN' if ok else 'RED'}", flush=True)
json.dump({"reply_time": rt, "wire_forwards": fwd_wire, "our_executions": ours,
           "checks": checks, "lead_labels": L.get("label_ids"),
           "activities": len(acts), "handovers": len(handovers)},
          open(os.path.join(HERE, "wf1-release-evidence", "b4b_resmoke.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if ok else 1)
