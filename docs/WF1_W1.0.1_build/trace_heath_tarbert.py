#!/usr/bin/env python3
"""READ ONLY. Person-8768306e (person 86369), FinovateFall - Noah - LinkedIn, 9 Sep ~14:50.

Parts 1-3 of the ask:
  1. what HeyReach ACTUALLY sent - the raw webhook body, message field, attachments, event type -
     and the same person's earlier invite event for comparison
  2. what WF-1 did with it: alert / registry row / label
  3. how many empty-message replies exist in the retained window, to size the rule

Executions are enumerated PER STATUS: the unfiltered /executions list under-reports here.
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
PERSON = 86369
NAME = "Person-8768306e"


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:140]}


def pd(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": "HTTP %s" % e.code}
    except Exception as e:
        if a < 3:
            time.sleep(3)
            return pd(p, a + 1)
        return {"__err": str(e)[:120]}


def all_execs(wfid, limit=250):
    out = {}
    for st in ("success", "error", "running", "waiting", "canceled"):
        cur = None
        while True:
            q = {"workflowId": wfid, "status": st, "limit": limit}
            if cur:
                q["cursor"] = cur
            d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q))
            for r in ((d or {}).get("data") or []):
                out[str(r["id"])] = r
            cur = (d or {}).get("nextCursor")
            if not cur:
                break
    return out


print("=" * 78)
print("Enumerating WF-1 executions in retention (per status)")
print("=" * 78)
ex = all_execs(WF1)
print("executions in retention: %d" % len(ex))
if ex:
    ts = sorted(str(r.get("startedAt")) for r in ex.values())
    print("window: %s  ->  %s" % (ts[0][:19], ts[-1][:19]))


def body_of(run):
    try:
        return (run["Webhook"][0]["data"]["main"][0][0].get("json") or {}).get("body") or {}
    except Exception:
        return {}


def items(run, nm):
    try:
        return [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
    except Exception:
        return []


MSG_KEYS = ("message", "message_text", "text", "body", "reply", "content", "last_message",
            "messageText")


def extract_msg(b):
    """Every plausible carrier of the message text, so 'empty' is a finding and not a bad guess."""
    found = {}
    for k in MSG_KEYS:
        if k in b:
            found[k] = b[k]
    lead = b.get("lead") or {}
    for k in MSG_KEYS:
        if isinstance(lead, dict) and k in lead:
            found["lead." + k] = lead[k]
    for k in ("messages", "conversation", "history", "attachments", "media"):
        if k in b:
            v = b[k]
            found[k] = ("<%s len=%d>" % (type(v).__name__, len(v))
                        if isinstance(v, (list, dict)) else v)
    return found


print("\n" + "=" * 78)
print("PART 1 - every retained execution mentioning %s / person %d" % (NAME, PERSON))
print("=" * 78)
mine, scanned = [], 0
cache = {}
for eid, row in sorted(ex.items(), key=lambda kv: str(kv[1].get("startedAt"))):
    f = n8n("/api/v1/executions/%s?includeData=true" % eid)
    cache[eid] = f
    scanned += 1
    blob = json.dumps(f, ensure_ascii=False)
    if NAME.lower() in blob.lower() or ('"%d"' % PERSON) in blob or (": %d" % PERSON) in blob:
        mine.append((eid, row))
    if scanned % 50 == 0:
        print("  scanned %d/%d" % (scanned, len(ex)), flush=True)
print("  scanned %d executions; %d touch the target" % (scanned, len(mine)))

for eid, row in mine:
    f = cache[eid]
    rd = (((f or {}).get("data") or {}).get("resultData") or {})
    run = rd.get("runData") or {}
    b = body_of(run)
    print("\n--- exec %s  %s  status=%s  nodes=%d ---" % (
        eid, str(row.get("startedAt"))[:19], row.get("status"), len(run)))
    print("    event_type   : %r" % b.get("event_type"))
    print("    campaign     : %r" % (b.get("campaign") or {}).get("name")
          if isinstance(b.get("campaign"), dict) else "    campaign     : %r" % b.get("campaign"))
    print("    top-level keys: %s" % sorted(b.keys()))
    print("    message carriers: %s" % json.dumps(extract_msg(b), ensure_ascii=False)[:700])
    lead = b.get("lead") or {}
    if isinstance(lead, dict):
        print("    lead keys    : %s" % sorted(lead.keys())[:18])
    for nm in ("Normalize", "M7 Alert Key", "M7 DT Alert Get", "M7 Alert Gate",
               "M7 IF Should Alert", "M7 Critical Slack", "M7 DT Alert Claim",
               "M7 DNC Reply Gate", "M7 DNC Build Input", "M7 DNC Upsert Call",
               "M7 Labels Compute", "M7 Lead Patch", "M7 Person Patch", "M7 Reply Activity"):
        if nm not in run:
            continue
        its = items(run, nm)
        print("    %-22s items=%d" % (nm[:22], len(its)))
        for it in its[:1]:
            if nm == "M7 Critical Slack":
                msg = it.get("message") or {}
                print("        channel=%s ts=%s" % (it.get("channel"), it.get("message_timestamp")))
                print("        text=%r" % str(msg.get("text") or "")[:400])
            else:
                keep = {k: v for k, v in it.items()
                        if k.startswith("__") or k in ("event", "message", "reason",
                                                       "reply_category", "correlation_id",
                                                       "pipedrive_person_id", "label_ids",
                                                       "claim_key", "family")}
                s = json.dumps(keep, ensure_ascii=False, default=str)
                print("        %s" % s[:500])

print("\n" + "=" * 78)
print("PART 3 - empty-message replies across the whole retained window")
print("=" * 78)
tally = {"reply_total": 0, "reply_empty": 0, "by_event": {}}
empties = []
for eid, f in cache.items():
    run = (((f or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    b = body_of(run)
    ev = str(b.get("event_type") or b.get("event") or "?")
    tally["by_event"][ev] = tally["by_event"].get(ev, 0) + 1
    if "REPL" not in ev.upper() and "MESSAGE" not in ev.upper():
        continue
    tally["reply_total"] += 1
    carriers = extract_msg(b)
    texts = [v for k, v in carriers.items()
             if isinstance(v, str) and k not in ("attachments", "media")]
    if not any((t or "").strip() for t in texts):
        tally["reply_empty"] += 1
        nm2 = ((b.get("lead") or {}).get("firstName") or "") + " " + \
              ((b.get("lead") or {}).get("lastName") or "")
        empties.append({"exec": eid, "event": ev, "who": nm2.strip(),
                        "carriers": {k: (v if isinstance(v, str) else str(v)[:40])
                                     for k, v in carriers.items()}})
print("  event types seen: %s" % json.dumps(tally["by_event"], ensure_ascii=False))
print("  reply-ish events : %d" % tally["reply_total"])
print("  EMPTY-message    : %d" % tally["reply_empty"])
for e in empties[:12]:
    print("     exec %-7s %-18s %-22s %s" % (e["exec"], e["event"], e["who"],
                                             json.dumps(e["carriers"], ensure_ascii=False)[:160]))

print("\n" + "=" * 78)
print("PART 2 - Pipedrive read-back for person %d" % PERSON)
print("=" * 78)
p = pd("/api/v2/persons/%d" % PERSON)
d = (p or {}).get("data") or {}
print("  name=%r owner=%s update_time=%s" % (d.get("name"), (d.get("owner") or {}).get("id"),
                                             d.get("update_time")))
leads = (pd("/v1/leads?limit=50&person_id=%d" % PERSON) or {}).get("data") or []
labnames = {x["id"]: x["name"] for x in ((pd("/v1/leadLabels") or {}).get("data") or [])}
for l in leads:
    print("  lead %s archived=%s owner_id=%s title=%r" % (l.get("id"), l.get("is_archived"),
                                                          l.get("owner_id"),
                                                          str(l.get("title"))[:64]))
    print("       labels=%s" % [labnames.get(x, x) for x in (l.get("label_ids") or [])])
acts = (pd("/api/v2/activities?limit=20&person_id=%d" % PERSON) or {}).get("data") or []
print("  activities: %d" % len(acts))
for a in acts[:6]:
    print("     %s %s %r" % (a.get("due_date"), a.get("type"), str(a.get("subject"))[:60]))

with open(os.path.join(HERE, "trace_heath_tarbert.json"), "w", encoding="utf-8") as f:
    json.dump({"executions_scanned": scanned, "target_execs": [e for e, _ in mine],
               "tally": tally, "empties": empties,
               "leads": leads, "person_owner": (d.get("owner") or {}).get("id")}, f,
              ensure_ascii=False, indent=1, default=str)
print("\n-> trace_heath_tarbert.json")
