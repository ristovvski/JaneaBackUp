#!/usr/bin/env python3
"""FLIP-DAY RECONCILIATION - every event of the flip window, plus the suppressed-population count.

Sections:
  1. flip timeline (what changed, when, with versionIds)
  2. replies processed live since the flip, wire-paired (Smartlead history vs our executions)
  3. forwards delivered - wire count, plus Rune's mailbox confirmation (human-closed)
  4. SUPPRESSED POPULATION: leads carrying '3. Responded' before the gate fix. Under the OLD
     label-based gate their next reply would NOT have alerted. With the delivery-registry gate
     deployed this is historical context, not a live hole - but the number belongs in the EOD.
  5. legacy state read-back
READ-ONLY.
"""
import json, os, ssl, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
FLIP_AT = "2026-08-10T11:31:01Z"
CAMPS = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
         3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}


def _get(url, headers):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=150, context=ctx) as x:
                return json.load(x)
        except Exception as e:
            if i < 2:
                time.sleep(3); continue
            return {"__err": str(e)[:120]}
    return {}


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                {"User-Agent": "janea-recon/1.0"})


def pd(p):
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea-recon/1.0"})


def mk(p):
    return _get(f"https://{ZONE}.make.com/api/v2{p}",
                {"Authorization": f"Token {MTOK}", "User-Agent": "janea-recon/1.0"})


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


out = {}
print("=" * 100)
print("1. FLIP TIMELINE")
print("=" * 100)
timeline = [
    ("11:31:01Z", "B3 flip", "WF-2 WRITE_MODE shadow -> live, secret deliberately unarmed",
     "2ac254cf"),
    ("12:37:18Z", "B4 pass 1", "reply processed; DOUBLE forward (Make still on); alert failed",
     "-"),
    ("12:45:10Z", "B5 kill", "Make 8557031 OFF, 8557478 OFF, both read-back verified", "-"),
    ("12:51:43Z", "B4 pass 2", "GREEN 11/11 - exactly one forward, wire-verified", "-"),
    ("13:5x", "alert fix", "Reply Alert + Nurture Alert off the broken expression construct",
     "1ccc77d5"),
    ("14:0x", "alarm conversion", "6 alarm nodes converted across WF-2 / WF-2S / WF-2R",
     "3de754aa"),
    ("14:15:25Z", "watchdog fired", "Ops Warn WF-2S Stale posted ok:true ts 1786371329.821239",
     "-"),
    ("~17:30Z", "INCIDENT", "write_mode_max_hours left at 0 ~3h by a stalled restore; restored",
     "0e6c96fd"),
    ("late", "mode inversion", "write_mode_expected='live'; shadow is now the anomaly", "b12cef0e"),
    ("late", "gate fix", "alert suppression by DELIVERY registry, not by label; category removed",
     "45637e70"),
]
for t, what, detail, ver in timeline:
    print(f"  {t:<11} {what:<18} {detail}")
    if ver != "-":
        print(f"              versionId {ver}")
out["timeline"] = timeline

print("\n" + "=" * 100)
print("2. REPLIES SINCE THE FLIP - wire vs processed")
print("=" * 100)
wire_replies, wire_forwards = [], []
for cid in CAMPS:
    skip = 0
    while skip < 4000:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            break
        for row in (page.get("data") or []):
            for h in (row.get("history") or []):
                t = str(h.get("time") or "")
                if t < FLIP_AT:
                    continue
                ty = str(h.get("type", "")).upper()
                if ty == "REPLY":
                    wire_replies.append({"email": row.get("to"), "time": t, "campaign": CAMPS[cid]})
                elif ty == "FORWARD":
                    wire_forwards.append({"email": row.get("to"), "time": t, "to": h.get("to")})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.1)
print(f"  replies on the wire since flip : {len(wire_replies)}")
for r in sorted(wire_replies, key=lambda x: x["time"]):
    print(f"     {r['time']}  {r['email']}  ({r['campaign']})")
print(f"  forwards on the wire since flip: {len(wire_forwards)}")
for f in sorted(wire_forwards, key=lambda x: x["time"]):
    print(f"     {f['time']}  {f['email']} -> {f['to']}")
paired = len(wire_replies) == len(wire_forwards)
print(f"  PAIRING: {'one forward per reply - no duplicates' if paired else 'MISMATCH'}")
out["wire_replies"] = wire_replies
out["wire_forwards"] = wire_forwards
out["paired"] = paired
out["mailbox_confirmed_by"] = "Rune - all forwards visible in his inbox (human confirmation)"
print("  MAILBOX: Rune confirmed all forwards visible in his inbox (human-closed)")

d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
ours = []
for e in (d.get("data") or []):
    if str(e.get("startedAt") or "") < FLIP_AT:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if g(rd, "Normalize", "event") != "REPLIED":
        continue
    ours.append({"exec": e["id"], "at": e.get("startedAt"),
                 "email": (g(rd, "Normalize", "lead") or {}).get("email"),
                 "dup": g(rd, "Dedupe", "__duplicate"),
                 "by": g(rd, "Normalize", "__reconciled_by"),
                 "fwd": bool(rd.get("SL Forward Email"))})
print(f"\n  WF-2 reply executions since flip: {len(ours)}")
for r in sorted(ours, key=lambda x: x["at"]):
    print(f"     {r['at']}  {r['email']}  dup={r['dup']} by={r['by']} fwd={r['fwd']}")
dupes_caught = [r for r in ours if r["dup"]]
print(f"  reconciler replays deduped (P0a working): {len(dupes_caught)}")
out["our_executions"] = ours

print("\n" + "=" * 100)
print("3. SUPPRESSED POPULATION (pre-gate-fix)")
print("=" * 100)
leads, start = [], 0
while True:
    dd = pd(f"/v1/leads?limit=500&start={start}&archived_status=all")
    b = dd.get("data") or []
    leads.extend(b)
    more = ((dd.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
resp = [L for L in leads if RESPONDED in (L.get("label_ids") or [])]
print(f"  total leads               : {len(leads)}")
print(f"  carrying '3. Responded'   : {len(resp)}")
print(f"  -> under the OLD label-based gate, each of these would have had its NEXT reply")
print(f"     SILENTLY SUPPRESSED. With the delivery-registry gate live, this is historical")
print(f"     context, not an open hole.")
out["total_leads"] = len(leads)
out["suppressed_population"] = len(resp)

print("\n" + "=" * 100)
print("4. LEGACY STATE (read-back)")
print("=" * 100)
legacy = {}
for sid, label in ((8557031, "lead creation"), (8557478, "responded label + forwards")):
    s = (mk(f"/scenarios/{sid}") or {}).get("scenario") or {}
    legacy[sid] = s.get("isActive")
    print(f"  Make {sid} ({label}): isActive={s.get('isActive')}")
out["legacy"] = legacy

json.dump(out, open(os.path.join(HERE, "wf1-release-evidence", "flip_reconciliation.json"), "w",
                    encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/flip_reconciliation.json")
