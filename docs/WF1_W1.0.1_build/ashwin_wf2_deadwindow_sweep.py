#!/usr/bin/env python3
"""READ-ONLY sweep: all Smartlead replies in the last 48h vs WF-2 n8n executions in the same
window. Lists any reply WF-2 never touched, then checks Pipedrive for a "responded"-side trace
(Make's job) to confirm business impact is zero. Also does a direct name/email lookup for
Person-b9e6150b specifically. No writes anywhere.
"""
import json, os, time
from datetime import datetime, timezone, timedelta
import urllib.request, urllib.parse, urllib.error

SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=48)

CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = None
if CA:
    import ssl
    ctx = ssl.create_default_context(cafile=CA)


def sl(path, params, tries=4):
    q = dict(params); q["api_key"] = SLK
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
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


def pd(path, params, tries=4):
    q = dict(params); q["api_token"] = PDT
    url = f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
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


def n8n(path, params, tries=4):
    q = urllib.parse.urlencode(params)
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})
            with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "body": e.read()[:300].decode(errors="replace")}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}
    return {}


CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}

print(f"Window: {SINCE.isoformat()} .. {NOW.isoformat()}")

# 1) Smartlead replies last 48h, per active email campaign
sl_replies = []
event_gt = SINCE.strftime("%Y-%m-%d")
for cid, name in CAMPS_EMAIL.items():
    offset = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": offset, "event_time_gt": event_gt})
        if "__err" in page:
            print(f"  [{cid}] ERROR: {page['__err']}"); break
        rows = page.get("data") if isinstance(page, dict) else page
        if not rows:
            break
        for r in rows:
            rt = r.get("last_reply_time") or r.get("reply_time")
            if rt:
                try:
                    rtd = datetime.fromisoformat(rt.replace("Z", "+00:00"))
                except Exception:
                    continue
                if SINCE <= rtd <= NOW:
                    sl_replies.append({"campaign_id": cid, "campaign": name, "email": r.get("email") or r.get("lead_email"),
                                        "lead_id": r.get("lead_id") or r.get("id"), "reply_time": rt,
                                        "category": r.get("lead_category") or r.get("category")})
        if len(rows) < 100:
            break
        offset += 100
        time.sleep(0.2)
print(f"Smartlead replies in window: {len(sl_replies)}")

# 2) Person-b9e6150b direct lookup (name match across replies + a direct Smartlead lead search)
ashwin_hits = [r for r in sl_replies if r.get("email") and "ashwin" in (r.get("email") or "").lower()]
print(f"Ashwin (by email substring in reply set): {len(ashwin_hits)}")
# broader: search smartlead leads by name across the 4 campaigns' lead lists (best-effort)
for cid, name in CAMPS_EMAIL.items():
    page = sl(f"/campaigns/{cid}/leads", {"limit": 200, "offset": 0})
    rows = page.get("data") if isinstance(page, dict) else page
    if isinstance(rows, list):
        for r in rows:
            ld = r.get("lead") or r
            full = f"{ld.get('first_name','')} {ld.get('last_name','')}".strip().lower()
            if "ashwin" in full and "deshpande" in full:
                print(f"  FOUND Person-b9e6150b in campaign {name}: email={ld.get('email')} lead_id={r.get('id') or ld.get('id')}")

# 3) WF-2 executions in window
execs = []
cursor = None
pages = 0
while pages < 30:
    params = {"workflowId": WF2, "limit": 100}
    if cursor:
        params["cursor"] = cursor
    page = n8n("/api/v1/executions", params)
    if "__err" in page:
        print("WF-2 executions error:", page); break
    data = page.get("data", [])
    for e in data:
        st = e.get("startedAt")
        if st:
            try:
                std = datetime.fromisoformat(st.replace("Z", "+00:00"))
            except Exception:
                continue
            if std >= SINCE:
                execs.append(e)
    cursor = page.get("nextCursor")
    pages += 1
    if not cursor or (data and datetime.fromisoformat(data[-1]["startedAt"].replace("Z", "+00:00")) < SINCE):
        break
print(f"WF-2 executions in window: {len(execs)} (across {pages} pages)")

# 4) cross-reference: does any WF-2 execution's data reference each reply email/lead_id?
exec_blob = json.dumps(execs, default=str)
unprocessed = []
for r in sl_replies:
    marker = r.get("email") or ""
    if marker and marker in exec_blob:
        continue
    unprocessed.append(r)
print(f"Replies with NO textual trace in any WF-2 execution payload: {len(unprocessed)}")

# 5) for each unprocessed, check Pipedrive for a responded-side trace (Make's job)
checked = []
for r in unprocessed[:60]:
    email = r.get("email")
    if not email:
        checked.append({**r, "pipedrive_trace": "NO_EMAIL"}); continue
    srch = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true"})
    items = ((srch or {}).get("data") or {}).get("items") or []
    if not items:
        checked.append({**r, "pipedrive_trace": "PERSON_NOT_FOUND"}); continue
    person_id = items[0]["item"]["id"]
    cl = pd(f"/persons/{person_id}/changelog", {"start": 0, "limit": 50})
    rows = (cl or {}).get("data") or []
    resp_hits = [x for x in rows if x.get("new_value") and "respond" in json.dumps(x.get("new_value")).lower()]
    checked.append({**r, "person_id": person_id, "pipedrive_trace": "RESPONDED_TRACE_FOUND" if resp_hits else "NO_RESPONDED_TRACE",
                     "changelog_sample": rows[:3]})
    time.sleep(0.15)

out = {"window": {"since": SINCE.isoformat(), "now": NOW.isoformat()},
       "sl_replies_count": len(sl_replies), "wf2_execs_count": len(execs),
       "unprocessed_count": len(unprocessed), "unprocessed_checked": checked,
       "ashwin_hits": ashwin_hits}
with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_wf2_deadwindow_sweep.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_wf2_deadwindow_sweep.json")
print(json.dumps({"sl_replies": len(sl_replies), "wf2_execs": len(execs),
                   "unprocessed": len(unprocessed),
                   "trace_summary": {k: sum(1 for c in checked if c.get("pipedrive_trace") == k)
                                     for k in ("RESPONDED_TRACE_FOUND", "NO_RESPONDED_TRACE", "PERSON_NOT_FOUND", "NO_EMAIL")}}, indent=2))
