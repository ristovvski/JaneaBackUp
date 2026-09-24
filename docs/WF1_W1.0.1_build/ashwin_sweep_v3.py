#!/usr/bin/env python3
"""READ-ONLY sweep v3 - step 4 rerun through NOW, with a PARSED cross-reference instead of the
v2 substring-over-blob check, plus the positive control v2 could not have: replies that arrived
AFTER WF-2 came back at 2026-08-05T06:42:59Z. If those processed and the earlier ones didn't, the
gap is outage-bounded rather than a permanent reply-path defect.

Processed-set is built from the SAME source the daily digest counts (WF-2 'Shadow Log' node
entries), so 'processed' here means exactly what the digest means by it. No writes anywhere.
"""
import json, os, ssl, time
from datetime import datetime, timedelta, timezone
import urllib.error, urllib.parse, urllib.request

SLK = os.environ["SMARTLEAD_API_KEY"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=72)
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None

# the documented WF-2 OOM dead window, from n8n's own execution record
DEAD_FROM = datetime.fromisoformat("2026-08-04T14:30:27+00:00")   # last crash of cluster 1
DEAD_TO = datetime.fromisoformat("2026-08-05T06:42:59+00:00")     # first success after recovery

CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}


def _get(url, headers, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}
    return {}


def sl(path, params):
    q = dict(params); q["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    return _get(f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}",
                {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


print(f"window: {SINCE.isoformat()} .. {NOW.isoformat()}  (72h)")
print(f"WF-2 documented dead window: {DEAD_FROM.isoformat()} .. {DEAD_TO.isoformat()}\n")

# ---------------------------------------------------------------- 1. Smartlead replies (truth)
replies = []
for cid, name in CAMPS_EMAIL.items():
    skip = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if "__err" in page:
            print(f"  [{cid}] ERROR {page['__err']}"); break
        rows = page.get("data") or []
        for row in rows:
            email = str(row.get("to") or "").strip().lower()
            for h in (row.get("history") or []):
                if h.get("type") != "REPLY":
                    continue
                t = ts(h.get("time"))
                if not t or not (SINCE <= t <= NOW):
                    continue
                replies.append({"campaign_id": cid, "campaign": name, "email": email,
                                "lead_id": row.get("lead_id"), "reply_time": t.isoformat(),
                                "_t": t, "subject": h.get("subject")})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.15)
replies.sort(key=lambda r: r["_t"])
print(f"Smartlead REPLY events in 72h: {len(replies)}")

# ------------------------------------------------- 2. WF-2 processed set, parsed from Shadow Log
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250})
execs = [e for e in (ex.get("data") or []) if ts(e.get("startedAt")) and ts(e["startedAt"]) >= SINCE]
print(f"WF-2 executions in 72h: {len(execs)}")

processed = {}       # email -> list of (exec_id, event, started)
shadow_rows = 0
for e in execs:
    dd = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((dd.get("data") or {}).get("resultData") or {}).get("runData") or {})
    for run in rd.get("Shadow Log") or []:
        try:
            items = run["data"]["main"][0]
        except Exception:
            continue
        for it in items or []:
            j = it.get("json") or {}
            shadow_rows += 1
            em = str(j.get("lead_email") or "").strip().lower()
            if em:
                processed.setdefault(em, []).append(
                    {"exec": e["id"], "event": j.get("event"), "started": e.get("startedAt"),
                     "node": j.get("node"), "campaign_id": j.get("campaign_id")})
    time.sleep(0.05)
print(f"Shadow Log rows parsed: {shadow_rows}; distinct lead emails seen by WF-2: {len(processed)}\n")

# --------------------------------------------------------------------------- 3. classify each
print(f"{'reply_time':<28} {'campaign':<20} {'zone':<12} {'WF-2':<9} email")
print("-" * 110)
rows_out = []
for r in replies:
    if r["_t"] < DEAD_FROM:
        zone = "before"
    elif r["_t"] <= DEAD_TO:
        zone = "IN-DEAD"
    else:
        zone = "after"
    hits = [h for h in processed.get(r["email"], [])
            if str(h.get("event", "")).lower().startswith("repl")]
    state = "processed" if hits else "MISSING"
    rows_out.append({**{k: v for k, v in r.items() if k != "_t"},
                     "zone": zone, "wf2": state, "wf2_hits": hits})
    print(f"{r['reply_time']:<28} {r['campaign']:<20} {zone:<12} {state:<9} {r['email']}")

miss = [r for r in rows_out if r["wf2"] == "MISSING"]
print(f"\nSmartlead replies (72h): {len(rows_out)} | processed by WF-2: {len(rows_out)-len(miss)}"
      f" | MISSING: {len(miss)}")
for z in ("before", "IN-DEAD", "after"):
    zr = [r for r in rows_out if r["zone"] == z]
    zm = [r for r in zr if r["wf2"] == "MISSING"]
    print(f"  zone {z:<8}: {len(zr)} replies, {len(zm)} missing")

with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_sweep_v3.json"), "w",
          encoding="utf-8") as f:
    json.dump({"window": {"since": SINCE.isoformat(), "now": NOW.isoformat()},
               "dead_window": {"from": DEAD_FROM.isoformat(), "to": DEAD_TO.isoformat()},
               "replies": rows_out, "wf2_exec_count": len(execs),
               "shadow_rows": shadow_rows}, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_sweep_v3.json")
