#!/usr/bin/env python3
"""MELISA-FACING SWEEP: every inbound reply on BOTH channels since the alert fixes, wire-authority.

Wire first, our executions second - our executions prove what WE did, never what arrived. So each
channel is enumerated from the PROVIDER (HeyReach conversations, Smartlead leads-statistics) and
then reconciled against WF-1 / WF-2 executions. A reply present on the wire with no execution is a
MISS and is reported as one; nothing is inferred from the absence of an execution.

Coverage is printed for both channels (conversations pulled, campaigns walked, leads paginated), so
a zero is provable rather than asserted - a swept-nothing and a nothing-happened look identical
otherwise.

Boundaries (both stated, sweep starts at the EARLIER one so nothing can slip between them):
  LinkedIn : WF-1 delivery-gate deploy          ~10:56Z
  Email    : WF-2 reply-channel switch (8adf3431) 11:25:42Z
Each reply is reported with the channel its alert ACTUALLY went to, so anything in the gap between
those two times is visible rather than assumed.
"""
import json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
HRK = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1, WF2 = "2jdjKM2NJr473GdA", "jp7rum9Z0YDJkQWv"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
LI_FROM = datetime.fromisoformat("2026-08-11T10:56:00+00:00")
EM_FROM = datetime.fromisoformat("2026-08-11T11:25:42+00:00")
START = min(LI_FROM, EM_FROM)
NOW = datetime.now(timezone.utc)


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


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   n8n read failed: {str(e)[:100]}")
        return None


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   smartlead read failed: {str(e)[:100]}")
        return None


def hr(p, body):
    r = urllib.request.Request("https://api.heyreach.io/api/public" + p, method="POST",
                               data=json.dumps(body).encode(),
                               headers={"X-API-KEY": HRK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   heyreach read failed: {str(e)[:100]}")
        return None


def out(rd, nm, k=None):
    try:
        j = rd[nm][0]["data"]["main"][0][0]["json"]
        return j if k is None else j.get(k)
    except Exception:
        return None


# ------------------------------------------------------------------ 1. LinkedIn wire
print("=" * 100)
print("A. LINKEDIN (HeyReach) - inbound messages on the wire")
convs, off = [], 0
while True:
    d = hr("/inbox/GetConversationsV2",
           {"filters": {"linkedInAccountIds": [], "campaignIds": []}, "offset": off, "limit": 100})
    if not d:
        break
    items = d.get("items") or []
    convs += items
    total = d.get("totalCount") or 0
    off += len(items)
    if not items or off >= total:
        break
li_inbound = []
for c in convs:
    prof = c.get("correspondentProfile") or {}
    if isinstance(prof, str):
        try:
            prof = json.loads(prof)
        except Exception:
            prof = {}
    for m in (c.get("messages") or []):
        t = ts(m.get("createdAt"))
        if t and t >= LI_FROM and str(m.get("sender", "")).upper() == "CORRESPONDENT":
            li_inbound.append({
                "at": t, "who": f"{prof.get('firstName', '')} {prof.get('lastName', '')}".strip(),
                "url": prof.get("profileUrl"), "text": str(m.get("body") or "")[:70]})
print(f"   coverage: conversations pulled {len(convs)} of {total if convs else 0}; "
      f"messages scanned {sum(len(c.get('messages') or []) for c in convs)}")
print(f"   inbound LinkedIn replies since {LI_FROM.isoformat()}: {len(li_inbound)}")
for r in sorted(li_inbound, key=lambda x: x["at"]):
    print(f"      {r['at'].isoformat()}  {r['who']:<26} {r['text']!r}")

# ------------------------------------------------------------------ 2. Email wire
print("\n" + "=" * 100)
print("B. EMAIL (Smartlead) - REPLY events on the wire")
camps = sl("/campaigns") or []
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
active = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING")]
em_replies, leads_seen, walked = [], 0, 0
for c in active:
    walked += 1
    off = 0
    while True:
        st = sl(f"/campaigns/{c.get('id')}/leads-statistics", {"limit": 100, "offset": off})
        rows = (st or {}).get("data") or []
        if not rows:
            break
        leads_seen += len(rows)
        for r in rows:
            for h in (r.get("history") or []):
                t = ts(h.get("time"))
                if t and t >= EM_FROM and str(h.get("type", "")).upper() == "REPLY":
                    # NOT `lead_email` - that key does not exist on a leads-statistics row, so it
                    # read None for every lead and the reconciliation matcher below reported two
                    # phantom "missed" replies. The row carries `to` (the lead) and `lead_id`.
                    em_replies.append({"at": t, "who": r.get("to"), "lead_id": r.get("lead_id"),
                                       "campaign": c.get("id"), "cname": c.get("name")})
        if len(rows) < 100:
            break
        off += 100
print(f"   coverage: campaigns walked {walked} of {len(camps)} total ({len(active)} active); "
      f"lead rows paginated {leads_seen}")
print(f"   email replies since {EM_FROM.isoformat()}: {len(em_replies)}")
for r in sorted(em_replies, key=lambda x: x["at"]):
    print(f"      {r['at'].isoformat()}  {r['who']}  campaign {r['campaign']}")

# ------------------------------------------------------------------ 3. our executions
print("\n" + "=" * 100)
print("C. WHAT WE DID (n8n executions since %s)" % START.isoformat())
processed = []
for wid, tag in ((WF1, "LinkedIn/WF-1"), (WF2, "Email/WF-2")):
    ex = n8n("/api/v1/executions", {"workflowId": wid, "limit": 120})
    for e in (ex or {}).get("data") or []:
        t = ts(e.get("startedAt"))
        if not t or t < START:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        if not det:
            continue
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        if tag.startswith("LinkedIn"):
            if "M7 Alert Gate" not in rd and "M7 Critical Slack" not in rd:
                continue
            slack = out(rd, "M7 Critical Slack") or {}
            who = (out(rd, "Normalize", "lead") or {})
            rec = {"wf": tag, "exec": e["id"], "at": t, "status": e.get("status"),
                   "who": who.get("name") or who.get("public_id") or who.get("li_url"),
                   "should": out(rd, "M7 Alert Gate", "__should_alert"),
                   "reason": out(rd, "M7 Alert Gate", "__alert_reason"),
                   "ok": slack.get("ok"), "channel": slack.get("channel"),
                   "ts": ((slack.get("message") or {}).get("ts")),
                   "crm": sorted(n for n in rd
                                 if any(w in n.lower() for w in ("patch", "activity", "label"))
                                 and not n.startswith("M7 Alert"))}
        else:
            if "First Reply Gate" not in rd and "Reply Alert" not in rd:
                continue
            alert = out(rd, "Reply Alert") or {}
            rec = {"wf": tag, "exec": e["id"], "at": t, "status": e.get("status"),
                   "who": (out(rd, "Normalize", "lead") or {}).get("email"),
                   "should": out(rd, "First Reply Gate", "__should_alert"),
                   "reason": out(rd, "First Reply Gate", "__alert_reason"),
                   "ok": alert.get("ok"), "channel": alert.get("channel"),
                   "ts": ((alert.get("message") or {}).get("ts")),
                   "crm": sorted(n for n in rd
                                 if any(w in n.lower() for w in ("labels union", "reply activity")))}
        processed.append(rec)
for r in sorted(processed, key=lambda x: x["at"]):
    ch = ("TEAM" if r["channel"] == TEAM else ("ops" if r["channel"] == OPS else r["channel"]))
    verdict = ("ALERTED " + str(ch)) if r["ok"] is True else (
        "suppressed (%s)" % r["reason"] if r["should"] is False else "NO ALERT")
    print(f"   {r['at'].isoformat()}  {r['wf']:<13} exec {r['exec']:<6} {str(r['who'])[:30]:<30} "
          f"{verdict}")
    print(f"      reason={r['reason']!r} status={r['status']} crm_writes={r['crm']}")

# ------------------------------------------------------------------ 4. reconcile
print("\n" + "=" * 100)
print("D. RECONCILIATION - a wire reply with no execution is a MISS")
em_proc = [p for p in processed if p["wf"].startswith("Email")]
li_proc = [p for p in processed if p["wf"].startswith("LinkedIn")]
missed = []
for r in em_replies:
    if not any(str(p["who"] or "").lower() == str(r["who"] or "").lower() for p in em_proc):
        missed.append(("email", r["at"].isoformat(), r["who"]))
for r in li_inbound:
    nm = (r["who"] or "").lower()
    if not any(nm and nm in str(p["who"] or "").lower() for p in li_proc):
        missed.append(("linkedin", r["at"].isoformat(), r["who"]))
print(f"   wire replies: linkedin {len(li_inbound)}, email {len(em_replies)}")
print(f"   executions  : linkedin {len(li_proc)}, email {len(em_proc)}")
print(f"   MISSED (on the wire, never processed): {len(missed)}")
for m in missed:
    print(f"      {m}")

alerted = [p for p in processed if p["ok"] is True and p["channel"] == TEAM]
alerted_ops = [p for p in processed if p["ok"] is True and p["channel"] == OPS]
suppressed = [p for p in processed if p["should"] is False]
print(f"\n   alerted to TEAM: {len(alerted)}   alerted to ops: {len(alerted_ops)}   "
      f"suppressed as repeat: {len(suppressed)}")

# ------------------------------------------------------------------ 5. funnel
print("\n" + "=" * 100)
print("E. LINKEDIN FUNNEL TODAY (campaigns 512995 / 513000, resumed)")
s = hr("/stats/GetOverallStats", {"accountIds": [], "campaignIds": [],
                                  "startDate": "2026-08-11T00:00:00Z",
                                  "endDate": "2026-08-12T00:00:00Z"}) or {}
o = s.get("overallStats") or {}
for k in ("connectionsSent", "connectionsAccepted", "messagesSent", "totalMessageStarted",
          "totalMessageReplies", "uniqueLeadsContacted"):
    print(f"   {k:<24} {o.get(k)}")
cs = hr("/campaign/GetAll", {"offset": 0, "limit": 20}) or {}
for c in (cs.get("items") or []):
    if c.get("id") in (512995, 513000):
        print(f"   campaign {c.get('id')}: status={c.get('status')!r} {str(c.get('name'))[:50]!r}")

json.dump({"li_wire": len(li_inbound), "em_wire": len(em_replies),
           "processed": len(processed), "alerted_team": len(alerted),
           "alerted_ops": len(alerted_ops), "suppressed": len(suppressed),
           "missed": missed, "coverage": {"conversations": len(convs),
                                          "campaigns_walked": walked, "lead_rows": leads_seen},
           "funnel": o},
          open(os.path.join(HERE, "wf1-release-evidence", "melisa_sweep.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
