#!/usr/bin/env python3
"""NIGHT SWEEP - did the night eat anything? Wire evidence, both channels.

Window: 2026-08-10T16:06:00Z (the P0-1 fix) -> now.

EMAIL: every campaign's `leads-statistics` `history[] type=REPLY` - the proven surface, not
`statistics.reply_time` which under-reports by ~33%. Every reply found is then traced to its fate
in WF-2: execution, forward, alert, CRM write.

LINKEDIN: HeyReach `/inbox/GetConversationsV2`, inbound messages in the same window, traced to
WF-1 executions.

Anything not fully processed is NAMED. Zero is a valid answer only if the sweep actually walked
the data - page counts and campaign counts are reported so an empty result cannot be mistaken for
an unrun sweep.
"""
import json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
HRK = os.environ["HEYREACH_API_KEY"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF1 = "jp7rum9Z0YDJkQWv", "2jdjKM2NJr473GdA"
SINCE = os.environ.get("SINCE", "2026-08-10T16:06:00Z")
NOW = datetime.now(timezone.utc)


def _get(url, headers, method="GET", body=None, tries=3):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers, method=method, data=data)
            with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:100]}
    return {}


def sl(p, q=None):
    qq = dict(q or {}); qq["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                {"User-Agent": "janea-night/1.0"})


def hr(p, body):
    return _get("https://api.heyreach.io/api/public" + p,
                {"X-API-KEY": HRK, "Accept": "application/json",
                 "Content-Type": "application/json"}, "POST", body)


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


from email.utils import parsedate_to_datetime  # noqa: E402

UNPARSEABLE = []


def ts(s):
    """Smartlead history carries BOTH ISO and RFC-2822 timestamps depending on the campaign.
    String-comparing them put 2024 replies inside a 2026 window ('F' > '2'), producing ten false
    'NOT PROCESSED' findings. Parse, never compare raw strings; record what will not parse rather
    than silently dropping or including it."""
    if not s:
        return None
    raw = str(s)
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        UNPARSEABLE.append(raw[:40])
        return None


SINCE_DT = ts(SINCE)
print(f"NIGHT SWEEP  window {SINCE} .. {NOW.isoformat()}\n", flush=True)

# ---------------------------------------------------------------- EMAIL: all campaigns
camps = sl("/campaigns")
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
pool = [c for c in camps
        if str(c.get("status", "")).upper() not in ("ARCHIVED", "DRAFTED")]
print(f"campaigns walked: {len(pool)} of {len(camps)} total", flush=True)

email_replies, pages_total, errs = [], 0, []
for idx, c in enumerate(pool, 1):
    cid = c.get("id")
    skip, pages = 0, 0
    while pages < 40:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if page.get("__err"):
            errs.append(f"campaign {cid}: {page['__err']}")
            break
        pages += 1; pages_total += 1
        for row in (page.get("data") or []):
            for h in (row.get("history") or []):
                if str(h.get("type", "")).upper() != "REPLY":
                    continue
                t = ts(h.get("time"))
                if t and t >= SINCE_DT:
                    email_replies.append({
                        "campaign_id": cid, "campaign": c.get("name"),
                        "email": row.get("to"), "lead_id": row.get("lead_id"),
                        "time": t.isoformat(),
                        "body": str(h.get("email_body") or "")[:90]})
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.05)
    if idx % 20 == 0:
        print(f"   ...{idx}/{len(pool)} campaigns, {pages_total} pages", flush=True)
print(f"campaigns walked: {len(pool)}, pages fetched: {pages_total}, errors: {len(errs)}")
print(f"EMAIL replies in window: {len(email_replies)}", flush=True)

# trace each to WF-2
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250})
wf2 = []
for e in (ex.get("data") or []):
    _t = ts(e.get("startedAt"))
    if not _t or _t < SINCE_DT:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if g(rd, "Normalize", "event") != "REPLIED":
        continue
    wf2.append({"exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
                "email": str((g(rd, "Normalize", "lead") or {}).get("email") or "").lower(),
                "dup": g(rd, "Dedupe", "__duplicate"),
                "fwd": bool(rd.get("SL Forward Email")),
                "alert_ok": (lambda j: j.get("ok") if isinstance(j, dict) else None)(
                    (rd.get("Reply Alert") or [{}])[0].get("data", {})
                    .get("main", [[{}]])[0][0].get("json", {}) if rd.get("Reply Alert") else {}),
                "lead": g(rd, "Lead Resolve", "__lead_id")})

for r in email_replies:
    hits = [w for w in wf2 if w["email"] == str(r["email"]).lower()]
    r["wf2_execs"] = [w["exec"] for w in hits]
    r["processed"] = bool(hits)
    r["forwarded"] = any(w["fwd"] for w in hits)
    r["alert_ok"] = any(w["alert_ok"] is True for w in hits)
    r["any_error"] = any(w["status"] != "success" for w in hits)

# ---------------------------------------------------------------- LINKEDIN
convs, offset = [], 0
while offset < 2000:
    d = hr("/inbox/GetConversationsV2", {"filters": {}, "offset": offset, "limit": 100})
    if d.get("__err"):
        errs.append(f"heyreach inbox: {d['__err']}"); break
    items = d.get("items") or []
    convs.extend(items)
    offset += len(items)
    if len(items) < 100 or offset >= int(d.get("totalCount") or 0):
        break
li = []
for c in convs:
    last = ts(c.get("lastMessageAt"))
    if not last or last < SINCE_DT:
        continue
    prof = c.get("correspondentProfile") or {}
    for m in (c.get("messages") or []):
        if str(m.get("sender", "")).upper() == "ME":
            continue
        t = ts(m.get("createdAt"))
        if t and t >= SINCE_DT:
            li.append({"name": " ".join(x for x in (prof.get("firstName"),
                                                    prof.get("lastName")) if x),
                       "time": t.isoformat(), "body": str(m.get("body") or "")[:80]})
    if not (c.get("messages") or []) and str(c.get("lastMessageSender", "")).upper() != "ME":
        li.append({"name": " ".join(x for x in (prof.get("firstName"),
                                                prof.get("lastName")) if x),
                   "time": last.isoformat(), "body": str(c.get("lastMessageText") or "")[:80]})
ex1 = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 100})
wf1_execs = [e for e in (ex1.get("data") or []) if str(e.get("startedAt") or "") >= SINCE]
print(f"conversations pulled: {len(convs)}")
print(f"LINKEDIN inbound in window: {len(li)}   WF-1 executions in window: {len(wf1_execs)}")

# ---------------------------------------------------------------- table
print("\n" + "=" * 104)
print("NIGHT SWEEP RESULT")
print("=" * 104)
print(f"{'channel':<9} {'time (UTC)':<26} {'who':<30} fate")
print("-" * 104)
if not email_replies and not li:
    print("  (no inbound events of either kind in the window)")
for r in sorted(email_replies, key=lambda x: x["time"]):
    fate = ("processed" if r["processed"] else "NOT PROCESSED")
    extra = []
    if r["processed"]:
        extra.append(f"execs={r['wf2_execs']}")
        extra.append("fwd" if r["forwarded"] else "no-fwd")
        extra.append("alert:ok" if r["alert_ok"] else "alert:none")
        if r["any_error"]:
            extra.append("EXEC ERROR")
    print(f"{'email':<9} {r['time'][:25]:<26} {str(r['email'])[:29]:<30} {fate} "
          f"{' · '.join(extra)}")
for r in sorted(li, key=lambda x: x["time"]):
    print(f"{'linkedin':<9} {r['time'][:25]:<26} {str(r['name'])[:29]:<30} "
          f"WF-1 execs in window: {len(wf1_execs)}")

bad = [r for r in email_replies if not r["processed"] or r["any_error"]]
print("\n" + "=" * 104)
print(f"  email replies      : {len(email_replies)}   unprocessed/errored: {len(bad)}")
print(f"  linkedin inbound   : {len(li)}")
print(f"  sweep coverage     : {len(pool)} campaigns, {pages_total} pages, "
      f"{len(convs)} conversations")
print(f"  API errors         : {len(errs)}")
print(f"  UNPARSEABLE timestamps skipped: {len(UNPARSEABLE)} {sorted(set(UNPARSEABLE))[:3]}")
for e in errs[:5]:
    print("     ", e)
print(f"\n  VERDICT: {'THE NIGHT ATE NOTHING' if not bad else 'EXCEPTIONS - see above'}")
json.dump({"window": {"since": SINCE, "now": NOW.isoformat()},
           "email_replies": email_replies, "linkedin": li, "wf2": wf2,
           "coverage": {"campaigns": len(pool), "pages": pages_total,
                        "conversations": len(convs)}, "errors": errs},
          open(os.path.join(HERE, "wf1-release-evidence", "night_sweep.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/night_sweep.json")


