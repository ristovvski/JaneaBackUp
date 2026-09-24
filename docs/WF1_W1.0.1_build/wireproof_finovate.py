#!/usr/bin/env python3
"""Wire proof for WF-2 c8a2050d: has a real SENT event run since the deploy, and did it produce a
LINKED lead with a PROVIDER name? Reports honestly if nothing has run yet."""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
ver = wf.get("versionId")
blc = next(n for n in wf["nodes"] if n["name"] == "Body Lead Create")["parameters"]["jsCode"]
ae = next(n for n in wf["nodes"] if n["name"] == "Apply Enrich")["parameters"]["jsCode"]
print(f"live WF-2 versionId : {ver}")
print(f"  pid waterfall live : {'Person Id Final' in blc}")
print(f"  name merge live    : {'merged.lead.first' in ae}")
print(f"  updatedAt          : {wf.get('updatedAt')}")

CUT = str(wf.get("updatedAt") or "")
print(f"\nlooking for SENT executions with a create path AFTER {CUT}\n")
cur, pages, after, before = None, 0, [], []
while pages < 6:
    q = {"workflowId": "jp7rum9Z0YDJkQWv", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if "Lead Create" not in rd:
            continue
        try:
            nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
            blcj = rd["Body Lead Create"][0]["data"]["main"][0][0]["json"]
            lc = rd["Lead Create"][0]["data"]["main"][0][0]["json"]
        except Exception:
            continue
        rec = {"exec": r["id"], "at": r.get("startedAt"),
               "email": (nz.get("lead") or {}).get("email"),
               "pid_in_body": (blcj.get("__body") or {}).get("person_id"),
               "lead_id": ((lc.get("data") or {}) or {}).get("id"),
               "campaign": str(nz.get("campaign_name"))[:40]}
        try:
            bpc = rd["Body Person Create"][0]["data"]["main"][0][0]["json"]
            b = bpc.get("__body") or {}
            rec["person_name"] = b.get("name") or f"{b.get('first_name')} {b.get('last_name')}"
            rec["from_provider"] = bpc.get("__name_from_provider")
        except Exception:
            rec["person_name"] = "(person already existed)"
            rec["from_provider"] = None
        (after if str(r.get("startedAt")) > CUT else before).append(rec)
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break

print(f"create-path executions AFTER the deploy : {len(after)}")
print(f"create-path executions BEFORE           : {len(before)}")
if not after:
    print("\n  ==> NO SENT EVENT HAS RUN THE CREATE PATH SINCE THE DEPLOY.")
    print("      Wire proof is NOT yet available. Nothing claimed.")
    if before:
        b = sorted(before, key=lambda x: str(x["at"]))[-1]
        print(f"      last pre-deploy create: exec {b['exec']} {b['at']}")
        print(f"        person_id in body = {b['pid_in_body']!r}  (the orphan symptom)")
        print(f"        person name       = {b['person_name']!r}")
else:
    ok = True
    for r in sorted(after, key=lambda x: str(x["at"])):
        linked = r["pid_in_body"] is not None
        good = linked and (r["from_provider"] is not False)
        ok = good and ok
        print(f"\n  [{'ok ' if good else 'FAIL'}] exec {r['exec']}  {r['at']}")
        print(f"        {r['email']}  ({r['campaign']})")
        print(f"        person_id in lead body : {r['pid_in_body']!r}   "
              f"{'LINKED' if linked else 'STILL ORPHANED'}")
        print(f"        person name written    : {r['person_name']!r} "
              f"from_provider={r['from_provider']}")
        if r["lead_id"]:
            l = (pd(f"/v1/leads/{r['lead_id']}") or {}).get("data") or {}
            print(f"        Pipedrive lead person_id = {l.get('person_id')!r}")
    print(f"\nWIRE PROOF: {'PASS' if ok else 'FAIL'}")
