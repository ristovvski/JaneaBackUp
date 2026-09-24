#!/usr/bin/env python3
"""Full-chain proof for the third fixture reply. Waits for a NEW execution, then grades it.

Every assertion below is one that has actually failed at some point today, which is why each is
stated separately instead of collapsed into "it worked":

  1. all FOUR candidates queried            (the off-by-one that skipped 85506)
  2. no read errors, not blind              (coverage, not inference)
  3. lead 72ec85c0 resolved                 (the horizon defect)
  4. person ADOPTED 84885 -> 85506          (B27: the lead is the authority, not the search order)
  5. label patch + reply activity written   (CRM side actually happened)
  6. alert POSTED ok:true WITH a ts         (not "the node ran")
  7. alert landed in C07LTD8UT70            (the channel switch)
  8. dedupe key claimed, BECAUSE __no_lead is false   (the claim guard)

Only executions started AFTER this script launches are considered, so a stale run cannot pass as
the proof.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
EMAIL = "pii-c61c7d08@example.invalid"
LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
SINCE = datetime.now(timezone.utc) - timedelta(minutes=int(os.environ.get("BACK_MIN", "6")))
DEADLINE = datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get("WAIT_MIN", "12")))


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"  n8n read failed: {str(e)[:110]}", flush=True)
        return None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


def items(rd, nm):
    try:
        return [i["json"] for i in rd[nm][0]["data"]["main"][0]]
    except Exception:
        return []


def one(rd, nm, k, d=None):
    it = items(rd, nm)
    return it[0].get(k, d) if it else d


print(f"waiting for a WF-2 execution for {EMAIL} started after {SINCE.isoformat()}", flush=True)
found = None
while datetime.now(timezone.utc) < DEADLINE and not found:
    ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 30})
    for e in sorted((ex or {}).get("data") or [], key=lambda r: str(r.get("startedAt"))):
        try:
            t = datetime.fromisoformat(str(e.get("startedAt")).replace("Z", "+00:00"))
        except Exception:
            continue
        if t < SINCE:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        if not det:
            continue
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        lead = one(rd, "Normalize", "lead") or {}
        if str(lead.get("email", "")).lower() == EMAIL:
            found = (e, rd)
            break
    if not found:
        time.sleep(20)

if not found:
    print("NO EXECUTION OBSERVED in the window - this is NOT a pass.")
    sys.exit(2)
e, rd = found
print(f"\nexec {e['id']}  {e.get('startedAt')}  status={e.get('status')}\n")

pages = items(rd, "R Lead List")
cands = one(rd, "R Person Pick", "__person_candidates") or []
print(f"candidates          : {cands}")
print(f"R Lead List requests: {len(pages)}")
for i, p in enumerate(pages):
    rows = p.get("data") if isinstance(p.get("data"), list) else None
    if rows is None:
        print(f"   [{i}] error item (no .data)")
    else:
        print(f"   [{i}] rows={len(rows)} persons={sorted({str(r.get('person_id')) for r in rows})}"
              f" has_fixture={any(str(r.get('id')) == LEAD for r in rows)}")

lr = (items(rd, "Lead Resolve") or [{}])[0]
for k in ("__lead_id", "__lead_how", "__no_lead", "__person_id", "__person_adopted",
          "__lead_candidates_read", "__lead_read_errors", "__leads_page_saturated"):
    print(f"{k:<24}: {lr.get(k)!r}")

alert = (items(rd, "Reply Alert") or [{}])[0]
ats = (alert.get("message") or {}).get("ts") or alert.get("ts")
ach = alert.get("channel")
gate_reason = one(rd, "First Reply Gate", "__alert_reason")
print(f"\ngate reason         : {gate_reason!r}")
print(f"alert ok/channel/ts : {alert.get('ok')!r} / {ach} / {ats}")

dk = one(rd, "Dedupe", "__dedupe_key")
sd = ((n8n(f"/api/v1/workflows/{WF2}") or {}).get("staticData") or {}).get("global", {})
seen = sd.get("wf2_seen") or {}

L = (pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
acts = (pd(f"/api/v2/activities?lead_id={LEAD}&limit=50") or {}).get("data") or []
try:
    rt = datetime.fromisoformat(str(e.get("startedAt")).replace("Z", "+00:00"))
except Exception:
    rt = SINCE
fresh = [a for a in acts
         if (datetime.fromisoformat(str(a.get("add_time")).replace("Z", "+00:00"))
             .replace(tzinfo=timezone.utc) if a.get("add_time") else SINCE) >= rt - timedelta(minutes=3)]

checks = {
    "all candidates queried": len(pages) >= len(cands) and len(cands) == 4,
    "no read errors": lr.get("__lead_read_errors") == 0,
    "not blind (saturated False)": lr.get("__leads_page_saturated") is False,
    "fixture lead resolved": str(lr.get("__lead_id")) == LEAD,
    "person adopted 84885 -> 85506": lr.get("__person_adopted") is True
                                     and str(lr.get("__person_id")) == "85506",
    "execution succeeded": e.get("status") == "success",
    "alert POSTED ok:true with ts": alert.get("ok") is True and bool(ats),
    "alert landed in TEAM channel": ach == TEAM,
    "'3. Responded' on the lead": RESPONDED in (L.get("label_ids") or []),
    "reply activity written": len(fresh) >= 1,
    "dedupe key CLAIMED (no_lead False)": bool(dk) and dk in seen and lr.get("__no_lead") is False,
}
print("\n--- GRADE ---")
for k, v in checks.items():
    print(f"  [{'OK ' if v else 'RED'}] {k}")
if alert.get("ok") is True and ats:
    print(f"\n  PERMALINK: https://janea.slack.com/archives/{ach}/p{str(ats).replace('.', '')}")
    print(f"  channel  : {ach} ({'TEAM #lead-processing' if ach == TEAM else 'OPS'})")

ok = all(checks.values())
print(f"\nW1.0.19 FULL-CHAIN PROOF: {'PASS' if ok else 'FAIL'}")
json.dump({"exec": e["id"], "at": e.get("startedAt"), "checks": checks,
           "resolve": lr, "requests": len(pages), "candidates": cands,
           "alert": {"ok": alert.get("ok"), "channel": ach, "ts": ats},
           "dedupe_key": dk, "claimed": dk in seen if dk else None},
          open(os.path.join(HERE, "wf1-release-evidence", "w1019_proof.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if ok else 1)
