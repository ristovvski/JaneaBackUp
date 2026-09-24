#!/usr/bin/env python3
"""Did the deployed Normalize actually key CRM writes to ANDREA, or to Marie-Anne again?

The 19:39 pair logged "person-side writes only" for HER. That message predates the fix on the first
exec; the question is what the LATER exec did, once lead.email := sl_lead_email was live.

Read the retained executions - do not assume the deploy worked. Checks, per exec:
  * which Normalize was in force (does the output carry __reply_class?)
  * lead.email  -> should be pii-eb7de9be@example.invalid AFTER the fix
  * __reply_from -> pii-10d2dcec@example.invalid
  * which person the CRM path actually resolved and wrote to
  * whether the alert fired and to which channel
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
GANGA = "pii-10d2dcec@example.invalid"
ANDREA = "pii-eb7de9be@example.invalid"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


ids = (n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60}) or {}).get("data") or []
found = []
for e in ids:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    if not rd:
        continue
    blob = json.dumps(rd)
    if GANGA not in blob and ANDREA not in blob:
        continue

    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None

    nz = o("Normalize") or {}
    found.append({"exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
                  "has_classifier": "__reply_class" in nz,
                  "cls": nz.get("__reply_class"),
                  "lead_email": (nz.get("lead") or {}).get("email"),
                  "reply_from": nz.get("__reply_from"),
                  "person": (o("R Person Pick") or {}).get("__person_id"),
                  "cands": (o("R Person Pick") or {}).get("__person_candidates"),
                  "lead_id": (o("Lead Resolve") or {}).get("__lead_id"),
                  "gate": (o("First Reply Gate") or {}).get("__alert_reason"),
                  "alert_ok": (o("Reply Alert") or {}).get("ok"),
                  "alert_ch": (o("Reply Alert") or {}).get("channel"),
                  "fwd": "SL Forward Email" in rd,
                  "nodes": len(rd)})

print(f"executions touching the Ganga/Andrea thread: {len(found)}\n")
for f in sorted(found, key=lambda r: str(r["at"])):
    print(f"exec {f['exec']}  {f['at']}  status={f['status']}  nodes={f['nodes']}")
    print(f"   classifier present : {f['has_classifier']}   class={f['cls']!r}")
    print(f"   lead.email         : {f['lead_email']!r}"
          f"{'   <-- ANDREA, correct' if f['lead_email'] == ANDREA else ''}"
          f"{'   <-- MARIE-ANNE, wrong human' if f['lead_email'] == GANGA else ''}")
    print(f"   __reply_from       : {f['reply_from']!r}")
    print(f"   person resolved    : {f['person']}  candidates={f['cands']}")
    print(f"   lead resolved      : {str(f['lead_id'])[:8] if f['lead_id'] else None}")
    print(f"   gate reason        : {f['gate']!r}   alert ok={f['alert_ok']} ch={f['alert_ch']}")
    print(f"   forwarded          : {f['fwd']}\n")

print("--- CRM state now ---")
for who, em in (("Andrea", ANDREA), ("Marie-Anne", GANGA)):
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(em)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or [] if pid else []
    print(f"   {who:<11} {em:<32} person={pid} leads={len(leads)}")
    for l in leads:
        print(f"      {str(l.get('id'))[:8]} labels={len(l.get('label_ids') or [])} "
              f"{str(l.get('title'))[:44]!r}")
