#!/usr/bin/env python3
"""Three confirms: the flagged key, 'dropped' semantics, drain ETA, and spacing on the wire.

1. The re-seed verifier flagged SENT|3756410|4295525421|1786398266965 as "crashed but claimed".
   Establish whether MY run claimed it or whether it was already claimed - the verifier cannot tell
   those apart, and the difference is everything.
2. "cap dropped N" - read the WF-2S code that produces it and prove whether dropped rows are
   DEFERRED (still in the pool next cycle) or DISCARDED.
3. Drain ETA from the real backlog and cap.
4. Spacing: consecutive WF-2 execution starts on the latest replay cycle should be ~10s apart.
   This is the done-criterion for the burst fix - read-back proved storage, only this proves effect.
"""
import json, os, re, ssl, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
FLAGGED = "SENT|3756410|4295525421|1786398266965"
NOW = datetime.now(timezone.utc)


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print("1. THE FLAGGED KEY - did I claim it, or was it already claimed?")
import glob
backups = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "wf2_backup_before_*.json")))
print(f"   backups on disk: {len(backups)}")
found_in = []
for b in backups[-8:]:
    try:
        d = json.load(open(b, encoding="utf-8"))
    except Exception:
        continue
    s = ((d.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
    if FLAGGED in s:
        found_in.append((os.path.basename(b), s[FLAGGED]))
for b, v in found_in:
    print(f"   present in {b}  value={v}")
print(f"   => {'ALREADY CLAIMED before tonight (pre-existing, NOT caused by the re-seed)' if found_in else 'NOT in any backup - investigate'}")
t = ts(datetime.fromtimestamp(1786398266.965, timezone.utc).isoformat())
print(f"   event time {t.isoformat()}  age {(NOW - t).total_seconds() / 3600:.1f}h  "
      f"(P0-1b deployed ~13:0xZ today, so this predates it)")

print("\n2. 'cap dropped N' - deferred or discarded?")
ws = n8n(f"/api/v1/workflows/{WF2S}")
for nm in ("Find New Sends", "Summary"):
    n = next((x for x in ws["nodes"] if x["name"] == nm), None)
    js = ((n or {}).get("parameters") or {}).get("jsCode") or ""
    for i, line in enumerate(js.splitlines(), 1):
        if any(w in line for w in ("drop", "cap", "max_per_run", "slice", "splice", "__sent_seen")):
            print(f"   {nm}:{i}| {line.strip()[:110]}")

print("\n3. DRAIN ETA")
sd = (ws.get("staticData") or {}).get("global") or {}
seen_v2 = len(sd.get("__sent_seen_v2") or {})
cfgn = next((x for x in ws["nodes"] if x["name"] == "CONFIG"), None)
raw = json.dumps((cfgn or {}).get("parameters") or {})
cap = int((re.search(r'\\"max_per_run\\":\s*(\d+)', raw) or [0, 20])[1])
w2 = n8n(f"/api/v1/workflows/{WF2}")
wseen = ((w2.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
print(f"   WF-2S __sent_seen_v2 (events it knows about): {seen_v2}")
print(f"   WF-2  wf2_seen (claimed/處理 done)          : {len(wseen)}")
print(f"   cap/cycle {cap}, cycle 15 min -> {cap * 4}/hour")

print("\n4. SPACING ON THE WIRE (the done-criterion)")
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
rows = sorted([(ts(e.get("startedAt")), e["id"]) for e in ((ex or {}).get("data") or [])
               if ts(e.get("startedAt"))], key=lambda r: r[0])
recent = [r for r in rows if (NOW - r[0]) < timedelta(minutes=40)]
print(f"   WF-2 executions in the last 40 min: {len(recent)}")
prev = None
gaps = []
for t, eid in recent:
    g = (t - prev).total_seconds() if prev else None
    if g is not None:
        gaps.append(g)
    print(f"      {t.strftime('%H:%M:%S')}  exec {eid}"
          + (f"   +{g:.1f}s" if g is not None else ""))
    prev = t
if gaps:
    burst = [g for g in gaps if g < 60]
    print(f"\n   consecutive gaps under 60s: {len(burst)}  "
          f"min={min(burst) if burst else '-'}  median="
          f"{sorted(burst)[len(burst) // 2] if burst else '-'}")
    if burst:
        ok = min(burst) >= 8
        print(f"   SPACING {'CONFIRMED (>=8s between consecutive replays)' if ok else 'NOT YET VISIBLE - gaps still sub-second'}")
    else:
        print("   no burst in this window - spacing unproven either way (not a pass)")
else:
    print("   no recent executions - spacing unproven (not a pass)")
