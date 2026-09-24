#!/usr/bin/env python3
"""Are the 32 crashed SENT events actually reachable by WF-2S - or did it already mark them seen?

I reported "32 recoverable" on the basis that their keys are unclaimed in WF-2's wf2_seen. That is
necessary but may NOT be sufficient: WF-2S decides what to replay from its OWN `__sent_seen_v2`, and
`Summary` writes that store AFTER `Replay Into WF-2` - i.e. on having SENT the replay, not on WF-2
having succeeded. If these events are already in __sent_seen_v2, WF-2S considers them done and will
never retry them, no matter how unclaimed they are downstream.

That would make "recoverable" false, so it gets checked rather than asserted.
"""
import json, os, re, ssl, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
SINCE = datetime.fromisoformat("2026-08-11T14:30:00+00:00")


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


print("A. how WF-2S decides what it has already handled")
ws = n8n(f"/api/v1/workflows/{WF2S}")
for nm in ("Find New Sends", "Summary"):
    n = next((x for x in ws["nodes"] if x["name"] == nm), None)
    js = ((n or {}).get("parameters") or {}).get("jsCode") or ""
    for i, line in enumerate(js.splitlines(), 1):
        if "__sent_seen_v2" in line or "seen[" in line or "seen." in line:
            print(f"   {nm}:{i}| {line.strip()[:112]}")

sd = (ws.get("staticData") or {}).get("global") or {}
sent_seen = sd.get("__sent_seen_v2") or {}
print(f"\n   __sent_seen_v2 entries: {len(sent_seen)}")
sample = list(sent_seen.items())[:3]
print(f"   sample keys: {json.dumps(sample, ensure_ascii=False)[:220]}")

print("\nB. the crashed SENT events - are they inside __sent_seen_v2?")
p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": "error"})
crashed = []
for e in ((p or {}).get("data") or []):
    if (ts(e.get("startedAt")) or SINCE) < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
        ded = rd["Dedupe"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    if nm.get("event") != "SENT":
        continue
    crashed.append({"exec": e["id"], "key": ded.get("__dedupe_key"),
                    "sl_lead": nm.get("sl_lead_id"), "camp": nm.get("campaign_id"),
                    "email": (nm.get("lead") or {}).get("email"),
                    "by": nm.get("__reconciled_by")})

w2 = n8n(f"/api/v1/workflows/{WF2}")
wseen = ((w2.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
blocked, reachable = [], []
for c in crashed:
    # WF-2S keys its store per campaign+lead; match on any key mentioning both
    hit = [k for k in sent_seen
           if str(c["camp"]) in str(k) and str(c["sl_lead"]) in str(k)]
    (blocked if hit else reachable).append(c)
print(f"   crashed SENT executions: {len(crashed)}")
print(f"   already in WF-2S __sent_seen_v2 (WF-2S will NOT retry): {len(blocked)}")
print(f"   not yet seen by WF-2S (it will pick them up)          : {len(reachable)}")
print(f"   arrived via replay (__reconciled_by set): "
      f"{sum(1 for c in crashed if c.get('by'))} of {len(crashed)}")
for c in blocked[:6]:
    print(f"      BLOCKED exec {c['exec']} camp={c['camp']} lead={c['sl_lead']} {c['email']}")

print("\nC. verdict")
if blocked:
    print(f"   *** {len(blocked)} crashed events are NOT self-recovering. WF-2S has already marked")
    print("       them seen, so 'unclaimed in wf2_seen' does not make them replayable. They need")
    print("       their WF-2S keys released, exactly like the WF-2 claims were.")
else:
    print("   all crashed events remain reachable by WF-2S - the earlier 'recoverable' claim holds.")
