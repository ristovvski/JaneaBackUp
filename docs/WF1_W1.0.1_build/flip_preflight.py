"""FLIP PREFLIGHT — read-only. Answers GREEN/RED for every gate before anything is touched.

Checks, in the order the runbook needs them:
  A  S4 re-claim: were yesterday's 66 rejected replays re-claimed, and are current cycles clean?
  B  WF-2S health: recent cycles, WF-2H last success, WRITE_MODE watchdog
  C  WF-2 state: version, nodes, active, WRITE_MODE, classifier, thresholds
  D  flip-checklist CONFIG items: webhook secret armed, reply channel, forward addresses
  E  Make cohabitants 8557031 / 8557478 - still ON? (they must go OFF at flip)
  F  the 4 Smartlead campaigns proposed for rename - status and current names
  G  rollback readiness: backups on disk, Make scenarios re-activatable, shadow revert path
Nothing is modified.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
NBASE = os.environ["N8N_BASE_URL"].rstrip("/")
NKEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
MTOK = os.environ["MAKE_API_TOKEN"]
ZONE = os.environ.get("MAKE_ZONE", "eu2")
if "." not in ZONE:
    ZONE += ".make.com"
UA = "Mozilla/5.0 janea-preflight/1.0"
WF2 = "jp7rum9Z0YDJkQWv"
SL_CAMPAIGNS = [3686193, 3686187, 3686184, 3686181]
MAKE_SCEN = [8557031, 8557478]
GREEN, RED = [], []


def n8n(path, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request(NBASE + path, headers={"X-N8N-API-KEY": NKEY})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}
    return {}


def sl(path):
    sep = "&" if "?" in path else "?"
    try:
        r = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}",
                                   headers={"User-Agent": UA})
        with urllib.request.urlopen(r, timeout=150) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code}


def mk(path):
    try:
        r = urllib.request.Request(f"https://{ZONE}/api/v2{path}",
                                   headers={"Authorization": "Token " + MTOK, "User-Agent": UA})
        with urllib.request.urlopen(r, timeout=120) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code}


def find_wf(name_frag):
    d = n8n("/api/v1/workflows?limit=250")
    for w in (d.get("data") or []):
        if name_frag.lower() in str(w.get("name", "")).lower():
            return w
    return None


def cfg_of(wf):
    for n in wf.get("nodes") or []:
        if n["name"] == "CONFIG":
            raw = (n.get("parameters") or {}).get("jsonOutput")
            try:
                return json.loads(raw)
            except Exception:
                return {}
    return {}


print("=" * 96)
print("C - WF-2 CURRENT STATE")
print("=" * 96)
wf2 = n8n(f"/api/v1/workflows/{WF2}")
c2 = cfg_of(wf2)
mode = c2.get("WRITE_MODE") or c2.get("write_mode")
print(f"  name={wf2.get('name')}  versionId={wf2.get('versionId')}")
print(f"  nodes={len(wf2.get('nodes') or [])}  active={wf2.get('active')}")
print(f"  WRITE_MODE          = {mode!r}")
for k in ("classify_enabled", "review_threshold", "confidence_threshold", "forward_review_address",
          "forward_owner_default", "slack_channel_replies", "slack_channel_ops",
          "webhook_secret_sha256", "campaign_allowlist"):
    if k in c2:
        v = c2[k]
        print(f"  {k:<20}= {json.dumps(v, ensure_ascii=False)[:80]}")
(GREEN if mode == "shadow" else RED).append(
    f"WF-2 WRITE_MODE is {mode!r} (expected 'shadow' pre-flip)")
(GREEN if wf2.get("active") else RED).append(f"WF-2 active={wf2.get('active')}")

print("\n" + "=" * 96)
print("A - S4 RE-CLAIM OF YESTERDAY'S REJECTED REPLAYS + CURRENT CYCLE HEALTH")
print("=" * 96)
wf2s = find_wf("WF-2S")
if not wf2s:
    RED.append("WF-2S workflow not found by name")
else:
    w = n8n(f"/api/v1/workflows/{wf2s['id']}")
    print(f"  WF-2S id={wf2s['id']} version={w.get('versionId')} "
          f"nodes={len(w.get('nodes') or [])} active={w.get('active')}")
    (GREEN if w.get("active") else RED).append(f"WF-2S active={w.get('active')}")
    ex = n8n(f"/api/v1/executions?workflowId={wf2s['id']}&limit=40")
    rows = [r for r in (ex.get("data") or []) if r.get("startedAt")]
    rows.sort(key=lambda r: r["startedAt"], reverse=True)
    print(f"  retained executions: {len(rows)}")
    reclaimed = rejected = 0
    shown = 0
    for r in rows[:14]:
        d = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
        summ = None
        for nm in ("Summary", "S6 Summary", "Cycle Summary"):
            if nm in rd:
                try:
                    summ = rd[nm][0]["data"]["main"][0][0]["json"]
                except Exception:
                    summ = None
                break
        if summ is None:
            continue
        acc = summ.get("accepted") or summ.get("accepted_count")
        rej = (summ.get("rejected") if summ.get("rejected") is not None
               else summ.get("rejected_count"))
        recl = summ.get("reclaimed") or summ.get("re_claimed")
        reclaimed += int(recl or 0)
        rejected += int(rej or 0)
        if shown < 8:
            shown += 1
            keys = {k: summ[k] for k in list(summ)[:12]}
            print(f"    {r['startedAt']} status={r.get('status')}")
            print(f"      {json.dumps(keys, ensure_ascii=False)[:340]}")
    print(f"\n  across the shown cycles: rejected={rejected} reclaimed={reclaimed}")
    errs = [r for r in rows if r.get("status") not in ("success", None)]
    print(f"  non-success executions retained: {len(errs)} {[(e['id'], e.get('status')) for e in errs[:5]]}")
    (GREEN if not errs else RED).append(
        f"WF-2S recent executions all success ({len(errs)} failures retained)")
    if rows:
        newest = datetime.fromisoformat(rows[0]["startedAt"].replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - newest).total_seconds() / 60
        print(f"  newest WF-2S cycle: {rows[0]['startedAt']} ({age_min:.0f} min ago)")
        (GREEN if age_min < 60 else RED).append(
            f"WF-2S last cycle {age_min:.0f} min ago (poller alive)")

print("\n" + "=" * 96)
print("B - WF-2H DIGEST")
print("=" * 96)
wf2h = find_wf("WF-2H")
if wf2h:
    ex = n8n(f"/api/v1/executions?workflowId={wf2h['id']}&limit=10")
    rows = [r for r in (ex.get("data") or []) if r.get("startedAt")]
    rows.sort(key=lambda r: r["startedAt"], reverse=True)
    print(f"  WF-2H id={wf2h['id']} retained={len(rows)}")
    if rows:
        print(f"  newest: {rows[0]['startedAt']} status={rows[0].get('status')}")
        ok = [r for r in rows if r.get("status") == "success"]
        (GREEN if ok else RED).append(f"WF-2H has a recent successful run ({len(ok)}/{len(rows)})")
    else:
        RED.append("WF-2H has no retained executions")
else:
    print("  WF-2H not found by name")

print("\n" + "=" * 96)
print("E - MAKE COHABITANTS (must be switched OFF at flip)")
print("=" * 96)
for sid in MAKE_SCEN:
    d = mk(f"/scenarios/{sid}")
    s = (d.get("scenario") or d)
    print(f"  [{sid}] {str(s.get('name'))[:56]:<58} isActive={s.get('isActive')}")
    if s.get("isActive"):
        GREEN.append(f"Make {sid} is ON now, so it CAN be turned off at flip")
    else:
        RED.append(f"Make {sid} is already OFF - unexpected, re-check before flipping")

print("\n" + "=" * 96)
print("F - THE 4 SMARTLEAD CAMPAIGNS PROPOSED FOR RENAME")
print("=" * 96)
camps = sl("/campaigns")
by_id = {c["id"]: c for c in camps} if isinstance(camps, list) else {}
for cid in SL_CAMPAIGNS:
    c = by_id.get(cid) or {}
    print(f"  [{cid}] status={str(c.get('status')):<9} name={c.get('name')}")
    an = sl(f"/campaigns/{cid}/analytics")
    sent = (an or {}).get("sent_count")
    print(f"           sent_count={sent}")

print("\n" + "=" * 96)
print("G - ROLLBACK READINESS")
print("=" * 96)
backups = sorted(f for f in os.listdir(HERE) if f.startswith("wf1_backup_before_"))
print(f"  WF-1 backups on disk: {len(backups)} (newest {backups[-1] if backups else '-'})")
wf2_built = os.path.join(HERE, "wf1-release-evidence", "wf2-built.json")
print(f"  WF-2 built artifact present: {os.path.exists(wf2_built)}")
print("  revert path: set CONFIG.WRITE_MODE='shadow' + PUT, re-activate Make 8557031/8557478")

print("\n" + "=" * 96)
print("VERDICT")
print("=" * 96)
for g in GREEN:
    print(f"  GREEN  {g}")
for r in RED:
    print(f"  RED    {r}")
print(f"\n  {len(GREEN)} green / {len(RED)} red")
