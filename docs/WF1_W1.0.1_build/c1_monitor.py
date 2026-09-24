#!/usr/bin/env python3
"""C1 - post-flip stabilization monitor. READ-ONLY.

Watches until the 2h clean bar is met (or an anomaly breaks it). Checks each pass:
  * every WF-2 reply execution succeeded, and forwarded at most ONCE per reply (wire-checked)
  * reconciler cycles clean (WF-2S / WF-2R), no stuck scan
  * Smartlead-truth vs processed delta stays 0
  * legacy Make scenarios stay OFF (a re-enable by anyone else is an anomaly)
  * WRITE_MODE stays live

Prints a three-liner on any anomaly and keeps going, so one blip does not hide later ones.
Exits 0 only if the full window was clean.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S, WF2R = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx", "U8Bb7Pdq7S6nzYPa"
CAMPS = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
         3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
FLIP_AT = os.environ.get("FLIP_AT", "2026-08-10T11:31:01Z")
# executions known to have failed AND to have been fixed. Named here so they stay visible in the
# record rather than being silently excluded by moving the window.
ACKNOWLEDGED = set((os.environ.get("ACK") or "").split(",")) - {""}
HOURS = float(os.environ.get("CLEAN_HOURS", "2"))
START = datetime.now(timezone.utc)
END = START + timedelta(hours=HOURS)


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
                {"User-Agent": "janea-c1/1.0"})


def mk(p):
    return _get(f"https://{ZONE}.make.com/api/v2{p}",
                {"Authorization": f"Token {MTOK}", "User-Agent": "janea-c1/1.0"})


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


anomalies, passes = [], 0
print(f"C1 monitor: clean bar {HOURS}h, until {END.strftime('%H:%M')}Z", flush=True)

while datetime.now(timezone.utc) < END:
    passes += 1
    found = []

    wf2 = n8n(f"/api/v1/workflows/{WF2}")
    cfg = json.loads(next(n for n in wf2["nodes"]
                          if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    if cfg.get("WRITE_MODE") != "live":
        found.append(f"WRITE_MODE is {cfg.get('WRITE_MODE')!r}, expected live")
    if wf2.get("active") is not True:
        found.append("WF-2 is not active")

    for sid in (8557031, 8557478):
        s = (mk(f"/scenarios/{sid}") or {}).get("scenario") or {}
        if s.get("isActive") is not False:
            found.append(f"legacy Make {sid} is back ON (isActive={s.get('isActive')})")

    # CONFIG INVARIANTS - production values, so a controlled fire whose restore never ran is
    # caught here within a cycle instead of by a human reading alarm spam hours later. A restore
    # that depends on the restoring process surviving is a hope, not a guarantee.
    INVARIANTS = {
        WF2S: {"wf2h_stale_hours": 48, "max_per_run": 20, "write_mode_expected": "live"},
        WF2R: {"wf2s_stale_minutes": 90, "max_per_run": 20, "max_campaigns_per_cycle": 1,
               "lookback_minutes": 2880, "max_pages_per_campaign": 35, "max_resume_rounds": 5},
        WF2: {"WRITE_MODE": "live"},
    }
    ABSENT = {WF2S: ["write_mode_max_hours"]}          # retired keys that must not come back
    for wid, wants in INVARIANTS.items():
        w = n8n(f"/api/v1/workflows/{wid}")
        node = next((n for n in w.get("nodes", []) if n["name"] == "CONFIG"), None)
        if not node:
            found.append(f"{wid}: CONFIG node not found")
            continue
        c = json.loads(node["parameters"]["jsonOutput"])
        for k, v in wants.items():
            if c.get(k) != v:
                found.append(f"CONFIG DRIFT {wid}: {k}={c.get(k)!r}, production value is {v!r}")
        for k in ABSENT.get(wid, []):
            if k in c:
                found.append(f"CONFIG DRIFT {wid}: retired key {k}={c.get(k)!r} is back")

    for wid, label in ((WF2S, "WF-2S"), (WF2R, "WF-2R")):
        d = n8n("/api/v1/executions", {"workflowId": wid, "limit": 8})
        rows = [e for e in (d.get("data") or []) if ts(e.get("startedAt"))
                and ts(e["startedAt"]) >= START - timedelta(minutes=40)]
        for e in rows:
            if e.get("status") != "success":
                found.append(f"{label} cycle {e['id']} status={e.get('status')}")
        if wid == WF2R:
            for e in rows[:2]:
                det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
                rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
                if g(rd, "Find New Replies", "__stuck") is True:
                    found.append(f"WF-2R scan STUCK on "
                                 f"{g(rd, 'Find New Replies', '__campaign_name')}")

    # reply executions since flip: success + at most one forward per lead
    d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
    fwd_by_lead = {}
    for e in (d.get("data") or []):
        if not ts(e.get("startedAt")) or str(e.get("startedAt")) < FLIP_AT:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        if g(rd, "Normalize", "event") != "REPLIED":
            continue
        # ACKNOWLEDGED: known-and-FIXED incidents are context, not recurring anomalies. Without
        # this a monitor with no watermark can never return clean after any incident - exec 14966
        # (the P0-1 crash, fixed at 16:06:14Z) was re-reported on 20 consecutive passes.
        if e.get("status") != "success" and str(e["id"]) not in ACKNOWLEDGED:
            found.append(f"WF-2 reply execution {e['id']} status={e.get('status')}")
        lead = (g(rd, "Normalize", "lead") or {}).get("email")
        if rd.get("SL Forward Email"):
            fwd_by_lead[lead] = fwd_by_lead.get(lead, 0) + 1
    # PAIR forwards to replies on the WIRE - do not count forwards per lead. Counting cumulative
    # forwards since the flip flagged 3 legitimate replies as a "DOUBLE FORWARD" on 24 consecutive
    # passes. A lead with N replies should have N forwards; only N+1 is a duplicate.
    for lead, n in fwd_by_lead.items():
        if not lead:
            continue
        replies_on_wire = 0
        for cid in CAMPS:
            d2 = sl("/leads", {"email": lead})
            lid = (d2 or {}).get("id")
            if not lid:
                continue
            h = (sl(f"/campaigns/{cid}/leads/{lid}/message-history") or {}).get("history") or []
            replies_on_wire += sum(
                1 for m in h
                if str(m.get("type", "")).upper() == "REPLY" and str(m.get("time", "")) >= FLIP_AT)
        if replies_on_wire and n > replies_on_wire:
            found.append(f"DOUBLE FORWARD: {lead} — {n} forwards for {replies_on_wire} replies "
                         f"since flip")
        elif not replies_on_wire and n > 1:
            found.append(f"FORWARDS WITHOUT WIRE REPLIES: {lead} — {n} forwards, 0 replies found")

    if found:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"\n[{stamp}Z] ANOMALY x{len(found)}", flush=True)
        for f in found:
            print(f"   • {f}", flush=True)
        anomalies.extend([{"at": stamp, "issue": f} for f in found])
    else:
        print(f"  pass {passes} clean at "
              f"{datetime.now(timezone.utc).strftime('%H:%M')}Z "
              f"(reply execs since flip: {len(fwd_by_lead)})", flush=True)
    time.sleep(300)

clean = not anomalies
print(f"\nC1: {'CLEAN' if clean else 'ANOMALIES'} over {HOURS}h — {passes} passes, "
      f"{len(anomalies)} anomaly record(s)", flush=True)
json.dump({"start": START.isoformat(), "end": datetime.now(timezone.utc).isoformat(),
           "passes": passes, "anomalies": anomalies, "clean": clean},
          open(os.path.join(HERE, "wf1-release-evidence", "c1_monitor.json"), "w",
               encoding="utf-8"), indent=2, default=str)
print("READY-FOR-FLIP-STABLE-CONFIRMED" if clean else "NOT READY — resolve anomalies first",
      flush=True)
sys.exit(0 if clean else 1)
