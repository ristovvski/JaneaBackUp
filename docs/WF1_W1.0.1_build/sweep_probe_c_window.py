#!/usr/bin/env python3
"""Did anything arrive while WF-2 was inactive because of my probe? Bound it and check the wire.

I deactivated WF-2 with a probe I had labelled harmless, and reactivated it a few minutes later.
While inactive its webhook is unregistered, so any Smartlead event in that window got a 404 and is
lost unless Smartlead retried. "Zero traffic all day" makes it probably empty - and probably is
exactly what Marine's OOO was.

HONEST BOUNDS: I did not timestamp the probe. The END of the window is knowable - WF-2's updatedAt
was set by my reactivation. The START is not, so the window is deliberately over-wide (updatedAt
minus PAD minutes), because a too-wide window can only produce false alarms, while a too-narrow one
produces false silence.

Smartlead only. Pipedrive is the auditor's until it reports.
"""
import json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
PAD = int(os.environ.get("PAD_MIN", "25"))


def get(url, hdr):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr),
                                    timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read FAILED (not empty): {str(e)[:110]}")
        return None


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    return get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
               {"User-Agent": "janea-sweep/1.0"})


def ts(v):
    if not v:
        return None
    s = str(v)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = parsedate_to_datetime(s)          # leads-statistics carries BOTH ISO and RFC-2822
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


wf = get(f"{BASE}/api/v1/workflows/jp7rum9Z0YDJkQWv", {"X-N8N-API-KEY": KEY})
end = ts((wf or {}).get("updatedAt"))
if not end:
    sys.exit("could not read WF-2 updatedAt - refusing to sweep an unbounded window")
start = end - timedelta(minutes=PAD)
print(f"WF-2 inactive window (over-wide by design): {start.isoformat()} .. {end.isoformat()}")
print(f"  end = WF-2.updatedAt (my reactivation); start = end - {PAD} min\n")

camps = (sl("/campaigns") or [])
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
active = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING")]
print(f"campaigns: {len(camps)} total, {len(active)} active/running")

hits, scanned, unparsed = [], 0, 0
for c in active:
    cid = c.get("id")
    st = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100})
    rows = (st or {}).get("data") or []
    for r in rows:
        for h in (r.get("history") or []):
            scanned += 1
            t = ts(h.get("time"))
            if t is None:
                unparsed += 1
                continue
            if start <= t <= end and str(h.get("type", "")).upper() in ("REPLY", "SENT"):
                hits.append({"campaign": cid, "name": c.get("name"), "type": h.get("type"),
                             "time": t.isoformat(), "lead": r.get("lead_email")
                             or r.get("lead_id")})

print(f"\nhistory entries scanned: {scanned}   unparseable timestamps: {unparsed}")
print(f"REPLY/SENT events inside the window: {len(hits)}")
for h in hits:
    print(f"   {h['time']}  {h['type']:<6} {h['lead']}  campaign {h['campaign']} {h['name']!r}")
print("\nVERDICT:", "CLEAN - nothing arrived while WF-2 was down"
      if not hits else "*** EVENTS LOST IN THE WINDOW - replay them via WF-2R ***")
if unparsed:
    print(f"NOTE: {unparsed} timestamps did not parse and were NOT silently treated as outside "
          f"the window - if that count is large, this sweep is not conclusive.")
