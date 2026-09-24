#!/usr/bin/env python3
"""Full fate trace for the ONE genuine overnight event: Person-cee23a2f's LinkedIn reply.

Also the FIRST live test of the C07LTD8UT70 channel switch - if his alert posted there, it is the
first message WF-1 has ever sent to the team channel.

Every comparison here is typed: datetimes parsed, channel compared as an exact string identity
(which it is), booleans compared as booleans. Coverage is printed so an empty answer cannot pass
as a clean one.
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
HRK = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
SLUG = "aneel-gillan"
SINCE = datetime.fromisoformat("2026-08-10T16:06:00+00:00")


def _get(url, headers, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    try:
        r = urllib.request.Request(url, headers=headers, method=method, data=data)
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def n8n(p, q=None):
    return _get(BASE + p + ("?" + urllib.parse.urlencode(q) if q else ""),
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def pd(p):
    return _get("https://api.pipedrive.com" + p,
                {"x-api-token": PDT, "User-Agent": "janea/1.0"})


def hr(p, body):
    return _get("https://api.heyreach.io/api/public" + p,
                {"X-API-KEY": HRK, "Accept": "application/json",
                 "Content-Type": "application/json"}, "POST", body)


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


def slug(u):
    s = str(u or "").split("?")[0].rstrip("/")
    return s.split("/in/")[-1].lower() if "/in/" in s else s.lower()


# ---- 1. the wire: HeyReach inbox
print("[1] HeyReach inbox — the event itself")
convs, offset = [], 0
while offset < 1000:
    d = hr("/inbox/GetConversationsV2", {"filters": {}, "offset": offset, "limit": 100})
    items = d.get("items") or []
    convs.extend(items)
    offset += len(items)
    if len(items) < 100 or offset >= int(d.get("totalCount") or 0):
        break
mine = [c for c in convs
        if slug((c.get("correspondentProfile") or {}).get("profileUrl")) == SLUG]
print(f"   conversations pulled: {len(convs)}   matching {SLUG}: {len(mine)}")
inbound = []
for c in mine:
    for m in (c.get("messages") or []):
        t = ts(m.get("createdAt"))
        if t and t >= SINCE and str(m.get("sender", "")).upper() != "ME":
            inbound.append({"time": t.isoformat(), "body": str(m.get("body") or "")[:120]})
    lt = ts(c.get("lastMessageAt"))
    if not (c.get("messages") or []) and lt and lt >= SINCE \
            and str(c.get("lastMessageSender", "")).upper() != "ME":
        inbound.append({"time": lt.isoformat(),
                        "body": str(c.get("lastMessageText") or "")[:120]})
for i in inbound:
    print(f"   REPLY {i['time']}  {i['body']!r}")

# ---- 2. WF-1 execution
print("\n[2] WF-1 execution")
d = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 40})
rows = []
for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
    t = ts(e.get("startedAt"))
    if not t or t < SINCE:
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    lead = g(rd, "Normalize", "lead") or {}
    if slug(lead.get("profile_url")) != SLUG:
        continue
    slack = {}
    for nm in rd:
        if "Slack" in nm or "Critical" in nm:
            try:
                j = rd[nm][0]["data"]["main"][0][0]["json"]
                slack = {"node": nm, "ok": j.get("ok"), "channel": j.get("channel"),
                         "ts": (j.get("message") or {}).get("ts")
                               if isinstance(j.get("message"), dict) else None,
                         "error": j.get("error")}
            except Exception:
                slack = {"node": nm, "ok": None}
    rows.append({"exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
                 "event": g(rd, "Normalize", "event"),
                 "should_alert": g(rd, "M7 Alert Gate", "__should_alert"),
                 "reason": g(rd, "M7 Alert Gate", "__alert_reason"),
                 "labels_changed": "M7 Lead Patch" in rd,
                 "reply_activity": "M7 Reply Activity" in rd,
                 "slack": slack})
print(f"   WF-1 executions for {SLUG} since {SINCE.isoformat()}: {len(rows)}")
for r in rows:
    print(f"   exec {r['exec']} {r['at']} status={r['status']} event={r['event']}")
    print(f"      should_alert={r['should_alert']} reason={r['reason']!r} "
          f"labels_patched={r['labels_changed']} reply_activity={r['reply_activity']}")
    print(f"      slack={r['slack']}")

# ---- 3. CRM read-back
print("\n[3] Pipedrive read-back")
srch = pd(f"/v1/persons/search?term={urllib.parse.quote('aneel-gillan')}&fields=custom_fields")
items = ((srch or {}).get("data") or {}).get("items") or []
pid = items[0]["item"]["id"] if items else 85155
leads = (pd(f"/v1/leads?limit=50&person_id={pid}&archived_status=all") or {}).get("data") or []
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
for L in leads:
    acts = (pd(f"/api/v2/activities?lead_id={L['id']}&limit=50") or {}).get("data") or []
    fresh = [x for x in acts if (ts(x.get("add_time")) or SINCE) >= SINCE]
    print(f"   lead {str(L['id'])[:8]} labels={L.get('label_ids')} "
          f"responded={RESPONDED in (L.get('label_ids') or [])}")
    print(f"      activities total={len(acts)} added since window={len(fresh)}")
    for x in fresh:
        print(f"         {x.get('add_time')} {str(x.get('subject'))[:50]!r} done={x.get('done')}")

# ---- 4. the channel question
print("\n[4] CHANNEL SWITCH — first live test of C07LTD8UT70")
posted = [r for r in rows if (r["slack"] or {}).get("ok") is True]
for r in posted:
    ch = r["slack"]["channel"]
    where = ("TEAM #lead-processing" if ch == TEAM
             else ("ops (Nik)" if ch == OPS else f"unknown {ch}"))
    tsv = str(r["slack"].get("ts") or "").replace(".", "")
    print(f"   posted ok=True to {ch} = {where}")
    if tsv:
        print(f"   permalink: https://janea.slack.com/archives/{ch}/p{tsv}")
if not posted:
    print("   NO alert posted with ok:true in this window")
    for r in rows:
        print(f"      exec {r['exec']}: should_alert={r['should_alert']} "
              f"reason={r['reason']!r} slack={r['slack']}")

json.dump({"inbound": inbound, "wf1": rows, "person_id": pid,
           "leads": [{"id": L["id"], "labels": L.get("label_ids")} for L in leads]},
          open(os.path.join(HERE, "wf1-release-evidence", "trace_aneel.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/trace_aneel.json")
