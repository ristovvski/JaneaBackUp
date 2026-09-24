#!/usr/bin/env python3
"""B4 - post-flip smoke watch. READ-ONLY.

Two jobs:
  1. Confirm a reconciler replay still authenticates now that WF-2 is live (unarmed path).
  2. Watch the 60-minute organic window for the first inbound reply and grade it against the FULL
     smoke criteria: categorized + forwarded ONCE to the CORRECT owner + one alert + lead written
     + correct label ID + Handover fires.

'Forwarded once' is checked by counting SL Forward Email calls for that reply across ALL WF-2
executions - a single execution looking right proves nothing about duplicates.
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
WF2, WF2R = "jp7rum9Z0YDJkQWv", "U8Bb7Pdq7S6nzYPa"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
FLIP_AT = os.environ.get("FLIP_AT", "2026-08-10T11:31:01Z")
WINDOW_MIN = int(os.environ.get("WINDOW_MIN", "60"))
START = datetime.now(timezone.utc)
DEADLINE = START + timedelta(minutes=WINDOW_MIN)


def _get(url, headers):
    try:
        r = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def pd(p):
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea-b4/1.0"})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


print(f"B4 watch: flip at {FLIP_AT}, organic window closes "
      f"{DEADLINE.strftime('%H:%M')}Z", flush=True)

# ---- 1. reconciler replay auth on the live workflow
print("\n[1] waiting for a WF-2R cycle to confirm replays still authenticate...", flush=True)
seen_auth = None
while datetime.now(timezone.utc) < START + timedelta(minutes=20) and seen_auth is None:
    d = n8n("/api/v1/executions", {"workflowId": WF2R, "limit": 5})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt")), reverse=True):
        if str(e.get("startedAt") or "") < FLIP_AT:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        seen_auth = {"cycle": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
                     "replayed": bool(rd.get("Replay Into WF-2"))}
        print(f"    WF-2R cycle {e['id']} {e.get('startedAt')} status={e.get('status')} "
              f"replayed={seen_auth['replayed']}", flush=True)
        break
    if seen_auth is None:
        time.sleep(60)

# any WF-2 execution since the flip, and whether it authenticated
d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 30})
post = [e for e in (d.get("data") or []) if str(e.get("startedAt") or "") >= FLIP_AT]
auth_rows = []
for e in sorted(post, key=lambda r: str(r.get("startedAt"))):
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    auth_rows.append({"id": e["id"], "at": e.get("startedAt"),
                      "auth_ok": g(rd, "Verify Secret", "__auth_ok"),
                      "mode": g(rd, "Verify Secret", "__auth_mode"),
                      "event": g(rd, "Normalize", "event"),
                      "reconciled_by": g(rd, "Normalize", "__reconciled_by"),
                      "write_mode": g(rd, "CONFIG", "WRITE_MODE")})
print(f"\n    WF-2 executions since flip: {len(auth_rows)}")
for r in auth_rows:
    print(f"      {r['at']} id={r['id']} auth_ok={r['auth_ok']} mode={r['mode']} "
          f"event={r['event']} by={r['reconciled_by']} WRITE_MODE={r['write_mode']}", flush=True)

# ---- 2. organic reply window
print(f"\n[2] watching for the first inbound reply until {DEADLINE.strftime('%H:%M')}Z...",
      flush=True)
found = None
while datetime.now(timezone.utc) < DEADLINE and not found:
    d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 30})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
        if str(e.get("startedAt") or "") < FLIP_AT:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        if g(rd, "Normalize", "event") != "REPLIED":
            continue
        lead = g(rd, "Normalize", "lead") or {}
        found = {
            "exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
            "email": lead.get("email"), "campaign": g(rd, "Normalize", "campaign_name"),
            "write_mode": g(rd, "CONFIG", "WRITE_MODE"),
            "category": g(rd, "Classify Parse", "__category"),
            "confidence": g(rd, "Classify Parse", "__confidence"),
            "forward_to": g(rd, "Forward Resolve", "__forward_to"),
            "forward_owner": g(rd, "Forward Resolve", "__forward_owner"),
            "forward_reason": g(rd, "Forward Resolve", "__forward_reason"),
            "forward_ran": bool(rd.get("SL Forward Email")),
            "lead_id": g(rd, "Lead Resolve", "__lead_id") or g(rd, "Merge Reply Ctx", "__lead_id"),
            "labels_written": g(rd, "Body Lead Labels Union", "__label_union"),
            "label_patch_ran": bool(rd.get("Lead Labels Union")),
            "activity_ran": bool(rd.get("Reply Activity")),
            "alert_ran": bool(rd.get("Reply Alert")),
            "should_alert": g(rd, "First Reply Gate", "__should_alert"),
        }
        break
    if not found:
        time.sleep(45)

out = {"flip_at": FLIP_AT, "auth_rows": auth_rows, "reconciler_cycle": seen_auth,
       "first_reply": found, "window_min": WINDOW_MIN}
if not found:
    print(f"\n    NO ORGANIC REPLY in {WINDOW_MIN} min -> ping Nik to reply in the "
          f"pii-c61c7d08@example.invalid thread", flush=True)
else:
    print("\n--- FIRST LIVE REPLY ---", flush=True)
    for k, v in found.items():
        print(f"    {k}: {v}", flush=True)
    # duplicate-forward check across ALL executions for this lead
    dupes = 0
    for e in sorted(post, key=lambda r: str(r.get("startedAt"))):
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        lead = g(rd, "Normalize", "lead") or {}
        if str(lead.get("email", "")).lower() == str(found["email"]).lower() \
                and rd.get("SL Forward Email"):
            dupes += 1
    out["forward_executions_for_this_lead"] = dupes
    print(f"    FORWARD SENT {dupes} time(s) - must be exactly 1", flush=True)
    if found.get("lead_id"):
        L = (pd(f"/v1/leads/{found['lead_id']}") or {}).get("data") or {}
        acts = (pd(f"/api/v2/activities?lead_id={found['lead_id']}&limit=50") or {}).get("data") or []
        out["lead_labels_now"] = L.get("label_ids")
        out["responded_present"] = RESPONDED in (L.get("label_ids") or [])
        out["handover_present"] = any(str(a.get("type")) == "handover" for a in acts)
        print(f"    lead labels now: {L.get('label_ids')}", flush=True)
        print(f"    RESPONDED present: {out['responded_present']}", flush=True)
        print(f"    Handover activity fired: {out['handover_present']}", flush=True)

json.dump(out, open(os.path.join(HERE, "wf1-release-evidence", "b4_smoke.json"), "w",
                    encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/b4_smoke.json", flush=True)
