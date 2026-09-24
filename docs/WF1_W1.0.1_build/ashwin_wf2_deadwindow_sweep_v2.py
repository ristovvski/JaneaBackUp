#!/usr/bin/env python3
"""READ-ONLY sweep v2 — CORRECTED after live shape verification (v1 silently reported 0 replies
due to a wrong-field bug: no top-level email/last_reply_time exist; replies are history[] entries
with type=="REPLY", lead email = row["to"]). All Smartlead replies in the last 48h vs WF-2 n8n
executions in the same window. Lists any reply WF-2 never touched, checks Pipedrive for a
responded-side trace. Also a direct name lookup for Person-b9e6150b. No writes anywhere.
"""
import json, os, time, ssl
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
ctx = ssl.create_default_context(cafile=CA) if CA else None


def _get(url, headers, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
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


def sl(path, params):
    q = dict(params); q["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}", {"User-Agent": UA})


def pd(path, params):
    q = dict(params); q["api_token"] = PDT
    return _get(f"https://janeasystems.pipedrive.com/api/v1{path}?{urllib.parse.urlencode(q)}", {"User-Agent": UA})


def n8n(path, params):
    q = urllib.parse.urlencode(params)
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    return _get(url, {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})


CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}

print(f"Window: {SINCE.isoformat()} .. {NOW.isoformat()}")

# 1) Smartlead replies last 48h, per active email campaign — CORRECTED extraction
sl_replies = []
all_replies_alltime = []  # for the Ashwin search (name isn't in leads-statistics; need /leads list)
for cid, name in CAMPS_EMAIL.items():
    skip = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if "__err" in page:
            print(f"  [{cid}] ERROR: {page['__err']}"); break
        rows = page.get("data") or []
        for row in rows:
            email = row.get("to")
            for h in (row.get("history") or []):
                if h.get("type") != "REPLY":
                    continue
                t = h.get("time")
                try:
                    td = datetime.fromisoformat(t.replace("Z", "+00:00"))
                except Exception:
                    continue
                rec = {"campaign_id": cid, "campaign": name, "email": email,
                       "lead_id": row.get("lead_id"), "reply_time": t, "subject": h.get("subject")}
                all_replies_alltime.append(rec)
                if SINCE <= td <= NOW:
                    sl_replies.append(rec)
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.15)
print(f"Smartlead REPLY events in 48h window: {len(sl_replies)}  (all-time REPLY events seen: {len(all_replies_alltime)})")
for r in sl_replies:
    print("  ", r["reply_time"], r["email"], "|", r["campaign"], "| lead", r["lead_id"])

# 2) Person-b9e6150b direct lookup (name isn't in leads-statistics rows; check via Pipedrive + Smartlead lead lists)
ashwin_pd = pd("/persons/search", {"term": "Person-b9e6150b", "fields": "name"})
items = ((ashwin_pd or {}).get("data") or {}).get("items") or []
print(f"\nAshwin Deshpande — Pipedrive person search: {len(items)} match(es)")
ashwin_email = None
for it in items:
    p = it["item"]
    print("  person_id", p["id"], p.get("name"), p.get("emails"))
    if p.get("emails"):
        ashwin_email = p["emails"][0]
if ashwin_email:
    hits = [r for r in all_replies_alltime if r["email"] and r["email"].lower() == ashwin_email.lower()]
    print(f"  Smartlead REPLY events for {ashwin_email}: {len(hits)}")
    for h in hits:
        print("   ", h["reply_time"], h["campaign"], h["subject"])

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
    stop = False
    for e in data:
        st = e.get("startedAt")
        if st:
            try:
                std = datetime.fromisoformat(st.replace("Z", "+00:00"))
            except Exception:
                continue
            if std >= SINCE:
                execs.append(e)
            else:
                stop = True
    cursor = page.get("nextCursor")
    pages += 1
    if not cursor or stop:
        break
print(f"\nWF-2 executions in window: {len(execs)} (across {pages} pages)")

# 4) cross-reference: does any WF-2 execution's data reference each reply email/lead_id?
# Pull execution DETAIL (with data) for each exec id, since list endpoint may omit payload.
exec_texts = []
for e in execs:
    detail = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    exec_texts.append(json.dumps(detail, default=str))
    time.sleep(0.1)
blob = "\n".join(exec_texts)

unprocessed = []
for r in sl_replies:
    marker = r.get("email") or ""
    if marker and marker in blob:
        continue
    unprocessed.append(r)
print(f"Replies with NO textual trace in any WF-2 execution payload: {len(unprocessed)}")
for r in unprocessed:
    print("   UNPROCESSED:", r["reply_time"], r["email"], r["campaign"])

# 5) for each unprocessed, check Pipedrive for a responded-side trace (Make's job)
checked = []
for r in unprocessed:
    email = r.get("email")
    if not email:
        checked.append({**r, "pipedrive_trace": "NO_EMAIL"}); continue
    srch = pd("/persons/search", {"term": email, "fields": "email", "exact_match": "true"})
    pitems = ((srch or {}).get("data") or {}).get("items") or []
    if not pitems:
        checked.append({**r, "pipedrive_trace": "PERSON_NOT_FOUND"}); continue
    person_id = pitems[0]["item"]["id"]
    cl = pd(f"/persons/{person_id}/changelog", {"start": 0, "limit": 50})
    rows = (cl or {}).get("data") or []
    checked.append({**r, "person_id": person_id, "changelog_rows": len(rows), "changelog_sample": rows[:5]})
    time.sleep(0.15)

out = {"window": {"since": SINCE.isoformat(), "now": NOW.isoformat()},
       "sl_replies_count": len(sl_replies), "sl_replies": sl_replies,
       "wf2_execs_count": len(execs), "unprocessed_count": len(unprocessed),
       "unprocessed_checked": checked, "ashwin_pd_matches": items}
with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_wf2_deadwindow_sweep_v2.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_wf2_deadwindow_sweep_v2.json")
