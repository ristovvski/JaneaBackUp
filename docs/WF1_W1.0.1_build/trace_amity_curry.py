#!/usr/bin/env python3
"""READ ONLY. End-to-end trace of the WF-2R replay for pii-9b2ca0d1@example.invalid (~17:46 local,
14:46Z, 2026-09-08) - the first real reply to exercise the 3-Sep DNC capture on the EMAIL side.

Four questions, each answered from a different system so no single source can flatter the result:
  1. reply category - real or OOO?            -> WF-2 classifier + First Reply Gate output
  2. alert posted to #lead-processing ONCE?   -> WF-2 Slack node output + the alert claim row
  3. reply_dnc row written via the new path?  -> DNC Reply Gate / Build Input / Upsert Call output,
                                                 plus the ledger sub-workflow's own execution
  4. label `3. Responded` set?                -> Pipedrive, read back directly

Executions are enumerated PER STATUS: the unfiltered /executions list under-reports here (it
returned 0 for a live execution earlier today).
"""
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
WF2R = "U8Bb7Pdq7S6nzYPa"
LEDGER = "RolYGL3J2CNg6Yp3"
TARGET = "pii-9b2ca0d1@example.invalid"


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:140]}


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": "HTTP %s %s" % (e.code, e.read()[:160].decode('utf-8', 'replace'))}
    except Exception as e:
        return {"__err": str(e)[:140]}


def execs(wfid, limit=40):
    out = {}
    for st in ("success", "error", "running", "waiting", "canceled"):
        d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
            {"workflowId": wfid, "status": st, "limit": limit}))
        for r in ((d or {}).get("data") or []):
            out[str(r["id"])] = r
    return out


def full(eid):
    return n8n("/api/v1/executions/%s?includeData=true" % eid)


def rundata(eid):
    f = full(eid)
    rd = (((f or {}).get("data") or {}).get("resultData") or {})
    return rd.get("runData") or {}, rd


def items(run, nm):
    try:
        return [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
    except Exception:
        return []


print("=" * 78)
print("STEP 0 - find the executions that touched %s" % TARGET)
print("=" * 78)
hits = []
for label, wfid in (("WF-2R", WF2R), ("WF-2", WF2), ("LEDGER", LEDGER)):
    ex = execs(wfid)
    print("\n%s: %d executions in retention" % (label, len(ex)))
    recent = sorted(ex.values(), key=lambda r: str(r.get("startedAt")), reverse=True)[:14]
    for r in recent:
        blob = json.dumps(full(r["id"]), ensure_ascii=False)
        touched = TARGET in blob
        if touched:
            hits.append((label, r))
        print("  %-7s id=%-7s %-8s %s  %s" % (
            label, r["id"], r.get("status"), str(r.get("startedAt"))[:19],
            "<== TOUCHES TARGET" if touched else ""))

if not hits:
    print("\nNo execution in retention mentions %s." % TARGET)
    sys.exit(2)

print("\n" + "=" * 78)
print("STEP 1-3 - what each execution decided")
print("=" * 78)
NODES_WF2 = ("Webhook", "Normalize", "SL Fetch Lead", "LLM Classify", "Classify Parse",
             "Alert Key", "DT Alert Get", "First Reply Gate", "IF Should Alert",
             "Body Reply Alert", "Critical Slack", "IF Alert Delivered", "DT Alert Claim",
             "DNC Reply Gate", "DNC Build Input", "DNC Upsert Call",
             "IF DNC", "U Lead DNC Label", "Body Lead Labels Union", "Lead Labels Patch",
             "Reply CRM Done", "Reply Activity", "Lead Patch Responded")
NODES_WF2R = ("Build REPLY Payload", "Post Replay", "Filter New Replies")

report = {}
for label, r in hits:
    run, rd = rundata(r["id"])
    print("\n--- %s exec %s (%s) nodes=%d ---" % (label, r["id"], r.get("status"), len(run)))
    if rd.get("error"):
        print("    ERROR: %s" % json.dumps(rd["error"], ensure_ascii=False)[:300])
    want = NODES_WF2 if label == "WF-2" else NODES_WF2R
    for nm in want:
        if nm not in run:
            continue
        its = items(run, nm)
        print("    %-24s items=%d" % (nm[:24], len(its)))
        for it in its[:1]:
            keep = {k: v for k, v in it.items()
                    if re.search(r"^__|category|ooo|alert|dnc|reason|label|lead_id|person|"
                                 r"to_email|sl_lead_email|correlation|ok$|ts$|channel", k, re.I)}
            if not keep:
                keep = {k: v for k, v in list(it.items())[:8]}
            s = json.dumps(keep, ensure_ascii=False, default=str)
            print("        %s" % (s[:900]))
    report[label + ":" + str(r["id"])] = {"status": r.get("status"),
                                          "started": r.get("startedAt"),
                                          "nodes": sorted(run)}

print("\n" + "=" * 78)
print("STEP 4 - Pipedrive: is the label actually set? (read back, do not infer)")
print("=" * 78)
s = pd("/api/v2/persons/search?fields=email&exact_match=true&limit=5&term="
       + urllib.parse.quote(TARGET))
its = ((s or {}).get("data") or {}).get("items") or []
if not its:
    print("  no person found for %s  (%s)" % (TARGET, json.dumps(s)[:160]))
else:
    pid = (its[0].get("item") or {}).get("id")
    print("  person_id=%s  name=%r" % (pid, (its[0].get("item") or {}).get("name")))
    leads = (pd("/v1/leads?limit=50&person_id=%s" % pid) or {}).get("data") or []
    print("  leads: %d" % len(leads))
    for l in leads:
        print("    lead %s  archived=%s  title=%r" % (l.get("id"), l.get("is_archived"),
                                                      str(l.get("title"))[:64]))
        print("      label_ids=%s" % l.get("label_ids"))
    lab = (pd("/v1/leadLabels") or {}).get("data") or []
    names = {x["id"]: x["name"] for x in lab}
    print("  label id -> name: %s" % json.dumps(
        {k: v for k, v in names.items()
         if any(k in (l.get("label_ids") or []) for l in leads)}, ensure_ascii=False))
    acts = (pd("/api/v2/activities?limit=20&person_id=%s" % pid) or {}).get("data") or []
    print("  activities on the person: %d" % len(acts))
    for act in acts[:6]:
        print("    %s  %s  %r" % (act.get("due_date"), act.get("type"),
                                  str(act.get("subject"))[:64]))

with open(os.path.join(HERE, "trace_amity_curry.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print("\n-> trace_amity_curry.json")
