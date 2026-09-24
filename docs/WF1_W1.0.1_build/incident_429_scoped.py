#!/usr/bin/env python3
"""429-storm, SCOPED to today's wave. The first pass counted 176 failures back to 2026-07-29.

Also answers the question that actually decides whether "recoverable" is true: WF-2S's
lookback_minutes is 180 (3h). A crashed SENT event is only recoverable while it is still inside that
window - being unclaimed is necessary but NOT sufficient. So this computes the DEADLINE for each
crashed event and whether the drain rate can reach it in time.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
SINCE = datetime.fromisoformat("2026-08-11T14:30:00+00:00")
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


p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250, "status": "error"})
rows = [e for e in ((p or {}).get("data") or []) if (ts(e.get("startedAt")) or SINCE) >= SINCE]
print(f"WF-2 errored executions since {SINCE.isoformat()}: {len(rows)}")

detail, nodes, errs = [], Counter(), Counter()
for e in rows:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    if not det:
        continue
    rdata = ((det.get("data") or {}).get("resultData") or {})
    rd = rdata.get("runData") or {}
    last = rdata.get("lastNodeExecuted")
    msg = str((rdata.get("error") or {}).get("message") or "")[:90]
    nodes[last] += 1
    errs[msg] += 1

    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return {}
    ded, nm = o("Dedupe"), o("Normalize")
    detail.append({"exec": e["id"], "at": ts(e.get("startedAt")), "node": last, "err": msg,
                   "event": nm.get("event"), "key": ded.get("__dedupe_key"),
                   "email": (nm.get("lead") or {}).get("email")})

print(f"\nfailing node:")
for n, c in nodes.most_common():
    print(f"   {str(n):<26} {c}")
print("errors:")
for m, c in errs.most_common():
    print(f"   [{c}x] {m}")
print(f"events: {Counter(d['event'] for d in detail)}")
if detail:
    tt = sorted(d["at"] for d in detail if d["at"])
    print(f"window: {tt[0].isoformat()} .. {tt[-1].isoformat()}")

wf = n8n(f"/api/v1/workflows/{WF2}")
seen = ((wf.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
withkey = [d for d in detail if d["key"]]
claimed = [d for d in withkey if d["key"] in seen]
print(f"\nRECOVERABILITY")
print(f"   crashed with a dedupe key : {len(withkey)}")
print(f"   UNCLAIMED (replayable)    : {len(withkey) - len(claimed)}")
print(f"   CLAIMED  (LOST)           : {len(claimed)}")
for d in claimed:
    print(f"      *** {d['key']}  exec {d['exec']} {d['email']}")

ws = n8n(f"/api/v1/workflows/{WF2S}")
cfgn = next((n for n in ws["nodes"] if n["name"] == "CONFIG"), None)
raw = json.dumps((cfgn or {}).get("parameters") or {})
import re
def num(field, default=None):
    m = re.search(rf'\\"{field}\\":\s*(\d+)', raw)
    return int(m.group(1)) if m else default
look = num("lookback_minutes", 180)
cap = num("max_per_run", 20)
sd = (ws.get("staticData") or {}).get("global") or {}
backlog = len(sd.get("__sent_seen_v2") or {})
print(f"\nWF-2S: lookback_minutes={look}  max_per_run={cap}  __sent_seen_v2={backlog}")
print(f"   cycle interval looks like 15 min -> drain ceiling ~{cap * 4}/hour")

print(f"\nDEADLINES (an unclaimed event is only recoverable INSIDE the {look}-minute lookback)")
sent = [d for d in detail if d["event"] == "SENT" and d["at"]]
if sent:
    for d in sorted(sent, key=lambda x: x["at"])[:3]:
        dl = d["at"] + timedelta(minutes=look)
        print(f"   earliest crashed SENT {d['at'].isoformat()} -> ages out {dl.isoformat()} "
              f"({(dl - NOW).total_seconds() / 60:.0f} min from now)")
        break
    d = sorted(sent, key=lambda x: x["at"])[-1]
    dl = d["at"] + timedelta(minutes=look)
    print(f"   latest   crashed SENT {d['at'].isoformat()} -> ages out {dl.isoformat()} "
          f"({(dl - NOW).total_seconds() / 60:.0f} min from now)")
    need = len(sent)
    print(f"\n   crashed SENT to recover: {need}; drain ceiling {cap}/cycle")
    print(f"   VERDICT: {'drains in time' if need <= cap * 4 else 'CAP TOO LOW - raise it'}")
