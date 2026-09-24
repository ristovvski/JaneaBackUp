"""Phase A pre-check (read-only): current WF-2S CONFIG + remaining SENT backlog size.

Answers, before touching anything:
  - current lookback_minutes / max_per_run
  - how much of the ~830-event backlog is STILL inside the current lookback window (i.e. still
    reachable) vs already aged out
  - what lookback would be needed to keep the whole backlog reachable at a 20/cycle drain rate
This determines what Phase A actually needs to set, rather than guessing.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
WF2S = "6Y92ryBwYoy6z0Jx"
UA = "Mozilla/5.0 janea-flipday/1.0"
CAMPS = [3686193, 3686187, 3686184, 3686181]
OUTAGE_START = "2026-08-04T14:45:00Z"     # first 404'd replay, per prior diagnosis


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def sl(path):
    sep = "&" if "?" in path else "?"
    r = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}",
                               headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=150) as x:
        return json.load(x)


wf = n8n(f"/api/v1/workflows/{WF2S}")
N = {n["name"]: n for n in wf["nodes"]}
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
print(f"WF-2S live version={wf.get('versionId')} active={wf.get('active')}")
print(f"current lookback_minutes = {cfg.get('lookback_minutes')}")
print(f"current max_per_run      = {cfg.get('max_per_run')}")
print(f"current max_campaigns_per_cycle = {cfg.get('max_campaigns_per_cycle')}")

now = datetime.now(timezone.utc)
lb_cut = (now - timedelta(minutes=int(cfg.get("lookback_minutes") or 180))).strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"\nlookback cutoff right now: {lb_cut}")
print(f"outage window: {OUTAGE_START} .. (reactivated ~2026-08-05T06:1x)")

total_sent_since_outage = 0
still_in_window = 0
for cid in CAMPS:
    off, rows = 0, []
    while True:
        st = sl(f"/campaigns/{cid}/statistics?offset={off}&limit=100")
        if not isinstance(st, dict) or st.get("__err"):
            break
        b = st.get("data") or []
        rows.extend(b)
        off += len(b)
        if len(b) < 100 or off >= int(st.get("total_stats") or 0):
            break
    since_outage = [r for r in rows if str(r.get("sent_time") or "") >= OUTAGE_START]
    in_window = [r for r in since_outage if str(r.get("sent_time") or "") >= lb_cut]
    total_sent_since_outage += len(since_outage)
    still_in_window += len(in_window)
    print(f"  [{cid}] sent since outage={len(since_outage)}  still inside current window={len(in_window)}")

print(f"\nTOTAL sent since outage start: {total_sent_since_outage}")
print(f"TOTAL still reachable at current lookback_minutes={cfg.get('lookback_minutes')}: {still_in_window}")
print(f"already aged out of the window (UNRECOVERABLE unless lookback stays wide): "
      f"{total_sent_since_outage - still_in_window}")

# how wide a lookback would keep the ENTIRE backlog reachable, from now
oldest = None
for cid in CAMPS:
    off = 0
    while True:
        st = sl(f"/campaigns/{cid}/statistics?offset={off}&limit=100")
        if not isinstance(st, dict) or st.get("__err"):
            break
        for r in st.get("data") or []:
            t = str(r.get("sent_time") or "")
            if t >= OUTAGE_START and (oldest is None or t < oldest):
                oldest = t
        off += len(st.get("data") or [])
        if len(st.get("data") or []) < 100 or off >= int(st.get("total_stats") or 0):
            break
if oldest:
    age_min = (now - datetime.fromisoformat(oldest.replace("Z", "+00:00"))).total_seconds() / 60
    print(f"\noldest still-outstanding SENT event: {oldest}  ({age_min:.0f} min ago)")
    print(f"lookback_minutes needed to keep it reachable RIGHT NOW: >= {int(age_min) + 30}")

# drain time at 20/cycle, 15-min cycles
per_cycle = 20
cycles_needed = -(-total_sent_since_outage // per_cycle)  # ceil
print(f"\nat max_per_run={per_cycle}, {total_sent_since_outage} events -> "
      f"~{cycles_needed} cycles -> ~{cycles_needed * 15} min to fully drain "
      f"({cycles_needed * 15 / 60:.1f}h)")
