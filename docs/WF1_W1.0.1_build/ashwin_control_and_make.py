#!/usr/bin/env python3
"""READ-ONLY. Two things v3 could not answer:

A. POSITIVE CONTROL - the 72h sweep found zero replies AFTER WF-2 recovered, so 'replies work
   again' is untested. Next best evidence: is the WF-2 webhook path delivering ANY event since
   06:42:59Z on 08-05? Break the Shadow Log down by event type and time.
   Also: were emails even being sent 08-05..08-06? Zero replies is only benign if sends continued.

B. STEP 5 - Make's own run history for the Ashwin reply, to confirm the business lost nothing.

No writes anywhere.
"""
import json, os, ssl, time
from datetime import datetime, timedelta, timezone
import urllib.error, urllib.parse, urllib.request

SLK = os.environ["SMARTLEAD_API_KEY"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
MAKE_TOKEN = os.environ["MAKE_API_TOKEN"]
MAKE_ZONE = os.environ.get("MAKE_ZONE", "eu2")
WF2 = "jp7rum9Z0YDJkQWv"
UA = "Mozilla/5.0 janea-forensics/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=72)
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
RECOVERY = datetime.fromisoformat("2026-08-05T06:42:59+00:00")

CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}


def _get(url, headers, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "__body": body}
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


def mk(path, params=None):
    q = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"https://{MAKE_ZONE}.make.com/api/v2{path}" + (f"?{q}" if q else "")
    return _get(url, {"Authorization": f"Token {MAKE_TOKEN}", "User-Agent": UA})


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


print("=" * 104)
print("A1. WF-2 Shadow Log broken down by event type and time (72h)")
print("=" * 104)
ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 250})
execs = [e for e in (ex.get("data") or []) if ts(e.get("startedAt")) and ts(e["startedAt"]) >= SINCE]
execs.sort(key=lambda e: e["startedAt"])
seen = []
for e in execs:
    dd = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((dd.get("data") or {}).get("resultData") or {}).get("runData") or {})
    nodes = list(rd.keys())
    ev = []
    for run in rd.get("Shadow Log") or []:
        try:
            items = run["data"]["main"][0]
        except Exception:
            continue
        for it in items or []:
            j = it.get("json") or {}
            ev.append({"event": j.get("event"), "node": j.get("node"),
                       "email": j.get("lead_email"), "campaign_id": j.get("campaign_id")})
    seen.append({"id": e["id"], "startedAt": e["startedAt"], "status": e.get("status"),
                 "mode": e.get("mode"), "n_nodes": len(nodes), "shadow": ev})
    time.sleep(0.05)

for s in seen:
    tag = "POST-RECOVERY" if ts(s["startedAt"]) > RECOVERY else "pre"
    evs = ", ".join(sorted({str(x["event"]) for x in s["shadow"]})) or "-"
    ems = ", ".join(sorted({str(x["email"]) for x in s["shadow"] if x["email"]})) or "-"
    print(f"  {s['startedAt']}  id={s['id']:<6} {s['status']:<9} mode={str(s['mode']):<9} "
          f"{tag:<14} events=[{evs}] emails=[{ems}]")

post = [s for s in seen if ts(s["startedAt"]) > RECOVERY]
post_shadow = [x for s in post for x in s["shadow"]]
post_webhook = [s for s in post if s["mode"] == "webhook"]
print(f"\n  executions post-recovery: {len(post)}  (webhook-mode: {len(post_webhook)})")
print(f"  shadow rows post-recovery: {len(post_shadow)}")
print(f"  event types post-recovery: {sorted({str(x['event']) for x in post_shadow}) or '(none)'}")

print("\n" + "=" * 104)
print("A2. Smartlead SENT volume per day per campaign (is 'zero replies since 08-05' benign?)")
print("=" * 104)
by_day = {}
for cid, name in CAMPS_EMAIL.items():
    skip = 0
    while True:
        page = sl(f"/campaigns/{cid}/leads-statistics", {"limit": 100, "offset": skip})
        if "__err" in page:
            print(f"  [{cid}] ERROR {page['__err']}"); break
        rows = page.get("data") or []
        for row in rows:
            for h in (row.get("history") or []):
                t = ts(h.get("time"))
                if not t or t < SINCE:
                    continue
                key = (t.date().isoformat(), name, h.get("type"))
                by_day[key] = by_day.get(key, 0) + 1
        if not page.get("hasMore"):
            break
        skip += 100
        time.sleep(0.15)
for key in sorted(by_day):
    print(f"  {key[0]}  {key[1]:<20} {str(key[2]):<6} {by_day[key]}")

print("\n" + "=" * 104)
print("B. Make - scenarios list, then run history around the Ashwin reply (2026-08-05T06:08:38Z)")
print("=" * 104)
orgs = mk("/organizations")
print("organizations:", json.dumps(orgs, default=str)[:400])
org_ids = [o.get("id") for o in (orgs.get("organizations") or [])]
scen_all = []
for oid in org_ids:
    teams = mk("/teams", {"organizationId": oid})
    for t in (teams.get("teams") or []):
        s = mk("/scenarios", {"teamId": t.get("id"), "pg[limit]": 100})
        for sc in (s.get("scenarios") or []):
            scen_all.append({"team": t.get("name"), "teamId": t.get("id"), "id": sc.get("id"),
                             "name": sc.get("name"), "isActive": sc.get("isActive"),
                             "scheduling": sc.get("scheduling")})
print(f"\nscenarios found: {len(scen_all)}")
for sc in scen_all:
    print(f"  [{ 'ON ' if sc['isActive'] else 'off'}] {sc['id']:<10} {sc['name']}")

out = {"wf2_execs": seen, "sent_by_day": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in by_day.items()},
       "make_scenarios": scen_all, "make_logs": {}}

for sc in scen_all:
    if not sc.get("id"):
        continue
    logs = mk(f"/scenarios/{sc['id']}/logs", {"pg[limit]": 50, "pg[sortDir]": "desc"})
    if logs.get("__err"):
        continue
    entries = logs.get("scenarioLogs") or []
    hits = []
    for L in entries:
        t = ts(L.get("timestamp"))
        if t and t >= SINCE:
            hits.append({"id": L.get("id"), "imtId": L.get("imtId"), "ts": L.get("timestamp"),
                         "status": L.get("status"), "operations": L.get("operations"),
                         "type": L.get("type"), "duration": L.get("duration")})
    if hits:
        out["make_logs"][str(sc["id"])] = {"name": sc["name"], "runs_72h": len(hits),
                                           "runs": hits[:25]}
        print(f"\n  scenario {sc['id']} '{sc['name']}' - {len(hits)} runs in 72h")
        for h in hits[:12]:
            print(f"     {h['ts']}  status={h['status']} ops={h['operations']} "
                  f"exec={h['imtId']}")
    time.sleep(0.1)

with open(os.path.join(HERE, "wf1-release-evidence", "ashwin_control_and_make.json"), "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/ashwin_control_and_make.json")
