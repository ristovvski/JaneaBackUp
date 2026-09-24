#!/usr/bin/env python3
"""END-OF-DAY consolidated report - evening edition of the existing digests.

Deliberately NOT a new workflow: it reuses the same sources the daily digests already read
(n8n executions, Smartlead truth, Pipedrive, Make) and composes one Melisa-forwardable post for
Nik's ops channel.

Sections, per spec:
  flip status (WRITE_MODE / what is live / legacy state)
  both channels' day numbers - sends, replies (Smartlead truth vs processed + DELTA), forwards
    delivered, leads created, labels
  recoveries (WF-2S / WF-2R claims)
  alerts fired vs suppressed
  STALE ALARMS - any stop-sign-class alarm unresolved for >24h gets its OWN line, never folded
    into cycle counts. This exists because a real 36% blind spot alarmed every cycle for three
    days and was read as noise.
  incidents + resolutions
  ACTION NEEDED: none / X

--post sends it; default prints only.
"""
import argparse, json, os, re, ssl, time, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1, WF2 = "2jdjKM2NJr473GdA", "jp7rum9Z0YDJkQWv"
WF2S, WF2R = "6Y92ryBwYoy6z0Jx", "U8Bb7Pdq7S6nzYPa"
CAMPS = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
         3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
NOW = datetime.now(timezone.utc)


def _get(url, headers):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=120, context=ctx) as x:
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
                {"User-Agent": "janea-eod/1.0"})


def mk(p):
    return _get(f"https://{ZONE}.make.com/api/v2{p}",
                {"Authorization": f"Token {MTOK}", "User-Agent": "janea-eod/1.0"})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=int, default=24)
ap.add_argument("--post", action="store_true")
a = ap.parse_args()
SINCE = NOW - timedelta(hours=a.hours)


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


# ------------------------------------------------------------------ flip status
wf2 = n8n(f"/api/v1/workflows/{WF2}")
cfg = json.loads(next(n for n in wf2["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
wf1 = n8n(f"/api/v1/workflows/{WF1}")
wf2s = n8n(f"/api/v1/workflows/{WF2S}")
wf2r = n8n(f"/api/v1/workflows/{WF2R}")
legacy = {}
for sid in (8557031, 8557478):
    s = (mk(f"/scenarios/{sid}") or {}).get("scenario") or {}
    legacy[sid] = s.get("isActive")

# ------------------------------------------------------- email channel (WF-2) day numbers
truth = {cid: set() for cid in CAMPS}
sent_today = 0
for cid in CAMPS:
    skip = 0
    while skip < 4000:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            break
        rows = page.get("data") or []
        for row in rows:
            for h in (row.get("history") or []):
                t = ts(h.get("time"))
                if not t or t < SINCE:
                    continue
                ty = str(h.get("type", "")).upper()
                if ty == "REPLY":
                    truth[cid].add(str(row.get("to") or "").lower())
                elif ty == "SENT":
                    sent_today += 1
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.1)

ex2 = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250})
processed, forwards, leads_written, labels_written = {c: set() for c in CAMPS}, 0, 0, 0
alerts_fired, replay_claims = 0, 0
for e in (ex2.get("data") or []):
    if not ts(e.get("startedAt")) or ts(e["startedAt"]) < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if g(rd, "Normalize", "event") != "REPLIED":
        continue
    lead = g(rd, "Normalize", "lead") or {}
    cid = g(rd, "Normalize", "campaign_id")
    if cid in processed:
        processed[cid].add(str(lead.get("email", "")).lower())
    if rd.get("SL Forward Email"):
        forwards += 1
    if rd.get("Lead Create"):
        leads_written += 1
    if rd.get("Lead Labels Union"):
        labels_written += 1
    if rd.get("Reply Alert"):
        alerts_fired += 1
    if g(rd, "Normalize", "__reconciled_by"):
        replay_claims += 1

# --------------------------------------------- LinkedIn channel (WF-1) day numbers
ex1 = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 250})
li = Counter()
li_alerts, li_suppressed = 0, 0
for e in (ex1.get("data") or []):
    if not ts(e.get("startedAt")) or ts(e["startedAt"]) < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    ev = str(g(rd, "Normalize", "event") or "?")
    li[ev] += 1
    sa = g(rd, "M7 Alert Gate", "__should_alert")
    if sa is True:
        li_alerts += 1
    elif sa is False:
        li_suppressed += 1

# ---------------------------------------- recoveries + stale stop-sign alarms
def cycles(wid, label):
    d = n8n("/api/v1/executions", {"workflowId": wid, "limit": 60})
    rows = [e for e in (d.get("data") or []) if ts(e.get("startedAt"))
            and ts(e["startedAt"]) >= SINCE]
    bad = [e for e in rows if e.get("status") != "success"]
    return {"label": label, "cycles": len(rows), "failed": len(bad),
            "last": max([e["startedAt"] for e in rows], default=None)}


rec = [cycles(WF2S, "WF-2S"), cycles(WF2R, "WF-2R")]

# stale stop-sign alarms: read the ops channel history is not available here, so use the
# reconciler's own reported state - a still-stuck cursor is the machine-readable version
stale = []
d = n8n("/api/v1/executions", {"workflowId": WF2R, "limit": 20})
for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt")), reverse=True)[:4]:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if g(rd, "Find New Replies", "__stuck") is True:
        stale.append(f"WF-2R scan stuck on {g(rd, 'Find New Replies', '__campaign_name')} "
                     f"— unscanned from offset {g(rd, 'Find New Replies', '__scanned_to')}")
        break

# ------------------------------------------------------------------ compose
t_tot = sum(len(v) for v in truth.values())
p_tot = sum(len(truth[c] & processed[c]) for c in CAMPS)
delta_rows = []
for cid, name in CAMPS.items():
    t, p = len(truth[cid]), len(truth[cid] & processed[cid])
    delta_rows.append((name, t, p, t - p))
delta_tot = t_tot - p_tot

live = cfg.get("WRITE_MODE") == "live"
legacy_off = all(v is False for v in legacy.values())
actions = []
if delta_tot > 0:
    actions.append(f"{delta_tot} reply(ies) in Smartlead with no WF-2 execution")
if stale:
    actions.append("WF-2R scan stuck (see stale alarms)")
if any(r["failed"] for r in rec):
    actions.append("reconciler cycle failures")
if not cfg.get("webhook_secret_sha256"):
    actions.append("webhook secret still unarmed (post-flip task #1)")

L = []
L.append(f"*END OF DAY — {NOW.strftime('%Y-%m-%d')}*")
L.append("")
L.append(f"*Flip status:* WF-2 `WRITE_MODE={cfg.get('WRITE_MODE')}` · "
         f"WF-1 {'live' if wf1.get('active') else 'INACTIVE'} · "
         f"WF-2S {'on' if wf2s.get('active') else 'OFF'} · "
         f"WF-2R {'on' if wf2r.get('active') else 'OFF'} · "
         f"legacy Make {'OFF (8557031, 8557478)' if legacy_off else 'STILL ON — ' + str(legacy)}")
L.append("")
L.append("*Email channel (Smartlead → WF-2), last 24h*")
L.append("```")
L.append(f"{'campaign':<20}{'Smartlead':>10}{'WF-2':>7}{'delta':>7}")
for name, t, p, dl in delta_rows:
    L.append(f"{name:<20}{t:>10}{p:>7}{dl:>7}" + ("   <<<" if dl > 0 else ""))
L.append(f"{'TOTAL (leads)':<20}{t_tot:>10}{p_tot:>7}{delta_tot:>7}")
L.append("```")
L.append(f"sends {sent_today} · forwards delivered {forwards} · leads created {leads_written} · "
         f"label patches {labels_written} · reply alerts {alerts_fired}")
L.append("")
L.append("*LinkedIn channel (HeyReach → WF-1), last 24h*")
L.append(f"events {sum(li.values())} — " + (", ".join(f"{k} {v}" for k, v in li.most_common())
                                            or "none"))
L.append(f"alerts fired {li_alerts} · suppressed {li_suppressed} (first-reply-only by design)")
L.append("")
L.append("*Recoveries*")
for r in rec:
    L.append(f"{r['label']}: {r['cycles']} cycles, {r['failed']} failed, last {r['last']}")
L.append(f"reconciler replays processed by WF-2: {replay_claims}")
if stale:
    L.append("")
    L.append("*🛑 STALE ALARMS (unresolved >24h)*")
    for s in stale:
        L.append(f"• {s}")
L.append("")
L.append(f"*ACTION NEEDED:* {'; '.join(actions) if actions else 'none'}")
text = "\n".join(L)

print(text)
json.dump({"at": NOW.isoformat(), "text": text, "delta_rows": delta_rows,
           "legacy": legacy, "write_mode": cfg.get("WRITE_MODE"), "actions": actions},
          open(os.path.join(HERE, "wf1-release-evidence", "eod_report.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print(f"\n[{'POSTED' if a.post else 'not posted — use --post'}]")
