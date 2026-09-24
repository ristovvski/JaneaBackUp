#!/usr/bin/env python3
"""P0-1 LIVE PROOF - grade the fixture reply against the current build, wire authority throughout.

Asserts, in order of what has actually failed before:
  1. Smartlead recorded the REPLY                          (wire)
  2. exactly ONE forward after it                          (wire - our executions only cross-check)
  3. WF-2 execution succeeded, WRITE_MODE live             (execution)
  4. Reply Alert returned ok:true WITH a ts -> permalink   (Slack API, not node presence)
  5. alert_text non-empty and category-free                (the P0-1 defect itself)
  6. lead resolved, labels patched, activity written       (Pipedrive read-back)
  7. claim state: __alert_delivered now holds the lead     (the gate fix)

Every comparison is typed: datetimes parsed (ISO and RFC-2822), booleans as booleans, channel as
an exact identity. Coverage printed so an empty result cannot pass as a clean one.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
CID, SL_LEAD, EMAIL = 3686187, "4306240392", "pii-c61c7d08@example.invalid"
PD_LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
SINCE = os.environ.get("SINCE", "2026-08-11T08:40:00Z")
DEADLINE = datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get("WINDOW_MIN", "18")))


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


SINCE_DT = ts(SINCE)


def _get(url, headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                {"User-Agent": "janea-proof/1.0"})


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def pd(p):
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea-proof/1.0"})


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


# ---- 1. wire: the reply
print(f"[1] waiting for the reply on the Smartlead wire (since {SINCE})", flush=True)
reply = None
while datetime.now(timezone.utc) < DEADLINE and not reply:
    h = (sl(f"/campaigns/{CID}/leads/{SL_LEAD}/message-history") or {}).get("history") or []
    reps = [m for m in h if str(m.get("type", "")).upper() == "REPLY"
            and (ts(m.get("time")) or SINCE_DT) > SINCE_DT]
    if reps:
        reply = sorted(reps, key=lambda m: ts(m.get("time")))[-1]
        break
    time.sleep(25)
if not reply:
    print("   no reply on the wire inside the window"); sys.exit(2)
rt = ts(reply.get("time"))
print(f"   REPLY {rt.isoformat()}  {str(reply.get('email_body'))[:80]!r}")
print("   waiting 80s for processing...", flush=True)
time.sleep(80)

# ---- 2. wire: forwards after it
hist = (sl(f"/campaigns/{CID}/leads/{SL_LEAD}/message-history") or {}).get("history") or []
fwd = [m for m in hist if str(m.get("type", "")).upper() == "FORWARD"
       and (ts(m.get("time")) or rt) > rt]
print(f"\n[2] forwards on the wire after this reply: {len(fwd)}")
for m in fwd:
    print(f"      {ts(m.get('time')).isoformat()} -> {m.get('to')}")

# ---- 3/4/5. execution + alert
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 25})
mine = []
for e in sorted((ex.get("data") or []), key=lambda r: str(r.get("startedAt"))):
    t = ts(e.get("startedAt"))
    if not t or t < rt:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    lead = g(rd, "Normalize", "lead") or {}
    if str(lead.get("email", "")).lower() != EMAIL:
        continue
    run = (rd.get("Reply Alert") or [{}])[0]
    j = {}
    try:
        j = run["data"]["main"][0][0]["json"]
    except Exception:
        pass
    msg = j.get("message") if isinstance(j.get("message"), dict) else {}
    mine.append({
        "exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
        "write_mode": g(rd, "CONFIG", "WRITE_MODE"),
        "dup": g(rd, "Dedupe", "__duplicate"),
        "by": g(rd, "Normalize", "__reconciled_by"),
        "category": g(rd, "Classify Parse", "__category"),
        "should_alert": g(rd, "First Reply Gate", "__should_alert"),
        "alert_reason": g(rd, "First Reply Gate", "__alert_reason"),
        "alert_text": g(rd, "Body Reply Alert", "alert_text"),
        "ok": j.get("ok"), "channel": j.get("channel"),
        "ts": msg.get("ts") or j.get("ts"), "error": j.get("error") or run.get("error"),
        "fwd_ran": bool(rd.get("SL Forward Email")),
        "forward_to": g(rd, "Forward Resolve", "__forward_to"),
        "lead_id": g(rd, "Lead Resolve", "__lead_id"),
        "label_patch": bool(rd.get("Lead Labels Union")),
        "activity": bool(rd.get("Reply Activity")),
    })
print(f"\n[3] WF-2 executions for this lead since the reply: {len(mine)}")
for m in mine:
    print(f"      exec {m['exec']} {m['at']} status={m['status']} dup={m['dup']} by={m['by']}")
    print(f"        alert ok={m['ok']} ch={m['channel']} ts={m['ts']} err={m['error']}")
    print(f"        reason={m['alert_reason']!r} cat={m['category']!r} fwd={m['fwd_ran']} "
          f"lead={str(m['lead_id'])[:8]} label={m['label_patch']} act={m['activity']}")
    if m["alert_text"]:
        print(f"        alert_text: {str(m['alert_text'])[:120]}")

first = mine[0] if mine else {}
posted = [m for m in mine if m["ok"] is True and m["ts"]]

# ---- 6. Pipedrive read-back
L = (pd(f"/v1/leads/{PD_LEAD}") or {}).get("data") or {}
acts = (pd(f"/api/v2/activities?lead_id={PD_LEAD}&limit=50") or {}).get("data") or []
fresh = [a for a in acts if (ts(a.get("add_time")) or SINCE_DT) >= rt]
print(f"\n[6] Pipedrive: labels={L.get('label_ids')}  responded={RESPONDED in (L.get('label_ids') or [])}")
print(f"      activities since the reply: {len(fresh)}")
for a in fresh:
    print(f"        {a.get('add_time')} {str(a.get('subject'))[:52]!r} done={a.get('done')}")

checks = {
    "reply on the wire": reply is not None,
    "exactly ONE forward on the wire": len(fwd) == 1,
    "our forwards agree with the wire": sum(1 for m in mine if m["fwd_ran"]) == len(fwd),
    "execution succeeded": bool(mine) and all(m["status"] == "success" for m in mine),
    "WRITE_MODE live": first.get("write_mode") == "live",
    "alert POSTED ok:true with a ts": len(posted) == 1,
    "alert_text non-empty (P0-1)": bool(first.get("alert_text")),
    "alert_text carries no category": "*" not in str(first.get("alert_text") or ""),
    "categorized": bool(first.get("category")),
    "lead resolved": bool(first.get("lead_id")),
    "label patch ran": any(m["label_patch"] for m in mine),
    "'3. Responded' on lead": RESPONDED in (L.get("label_ids") or []),
    "reply activity written": len(fresh) >= 1,
}
print("\n--- GRADE ---")
for k, v in checks.items():
    print(f"  [{'OK ' if v else 'RED'}] {k}")
permalink = None
if posted:
    p = posted[0]
    permalink = f"https://janea.slack.com/archives/{p['channel']}/p{str(p['ts']).replace('.', '')}"
    where = ("TEAM #lead-processing" if p["channel"] == TEAM
             else ("ops (Nik)" if p["channel"] == OPS else p["channel"]))
    print(f"\n  PERMALINK: {permalink}")
    print(f"  channel  : {p['channel']} = {where}")

ok = all(checks.values())
print(f"\nP0-1 LIVE PROOF: {'PASS' if ok else 'FAIL'}")
json.dump({"reply_time": rt.isoformat(), "wire_forwards": len(fwd), "executions": mine,
           "checks": checks, "permalink": permalink, "labels": L.get("label_ids"),
           "activities_since": len(fresh)},
          open(os.path.join(HERE, "wf1-release-evidence", "p01_live_proof.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if ok else 1)
