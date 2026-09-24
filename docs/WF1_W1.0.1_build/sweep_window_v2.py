#!/usr/bin/env python3
"""CORRECTED outage sweep. My first one was anchored to the wrong clock.

I used WF-2's `updatedAt` as the end of the inactive window, believing my reactivation set it. The
auditor's bracket shows updatedAt 11:25:42Z / versionCounter 460 is the CHANNEL-SWITCH PUT - n8n's
activate/deactivate do NOT bump updatedAt. So my window (11:00:42 - 11:25:42Z) sat entirely BEFORE
the outage, and its "CLEAN" verdict was evidence about the wrong minutes.

Honest bounds this time, from facts I can actually stand on:
  start = 11:25:42Z  - the last accepted write; everything after it is suspect
  end   = now        - covers the reactivation and everything since
Deliberately far too wide: an over-wide window can only raise false alarms, a narrow one
manufactures false silence. Smartlead only (Pipedrive is the auditor's).
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
START = datetime.fromisoformat(os.environ.get("WIN_START", "2026-08-11T11:25:42+00:00"))
END = datetime.now(timezone.utc)


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                headers={"User-Agent": "janea-sweep/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read FAILED (not empty): {str(e)[:110]}")
        return None


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
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print(f"window: {START.isoformat()} .. {END.isoformat()}  "
      f"({(END - START).total_seconds() / 60:.0f} min, intentionally over-wide)")
camps = sl("/campaigns") or []
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
active = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING")]
print(f"campaigns: {len(camps)} total, {len(active)} active\n")

hits, scanned, unparsed = [], 0, 0
for c in active:
    st = sl(f"/campaigns/{c.get('id')}/leads-statistics", {"limit": 100})
    for r in ((st or {}).get("data") or []):
        for h in (r.get("history") or []):
            scanned += 1
            t = ts(h.get("time"))
            if t is None:
                unparsed += 1
                continue
            if START <= t <= END and str(h.get("type", "")).upper() in ("REPLY", "SENT"):
                hits.append((t.isoformat(), h.get("type"),
                             r.get("lead_email") or r.get("lead_id"), c.get("id"), c.get("name")))

print(f"history entries scanned: {scanned}   unparseable: {unparsed}")
print(f"REPLY/SENT in window: {len(hits)}")
for h in sorted(hits):
    print(f"   {h[0]}  {h[1]:<6} {h[2]}  campaign {h[3]} {h[4]!r}")
print("\nVERDICT:", "CLEAN - nothing arrived in the corrected window"
      if not hits else "*** EVENTS IN WINDOW - check whether WF-2 was down for them ***")
