#!/usr/bin/env python3
"""Person-9979a87c IS person 85517. A plain term search finds him; WF-1's M7 resolver did not.
So the alert's 'not in Pipedrive' is FALSE - it is a match miss, not an absence.

Find the exact mismatch: what LinkedIn value does the person actually carry, and what did M7 send?
Read M7's two search nodes' real request URLs from the execution, not from the workflow definition -
the expression's RESULT is what matters.
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


print("=== person 85517 as Pipedrive actually stores him ===")
p = (pd("/api/v2/persons/85517") or {}).get("data") or {}
print(f"  name={p.get('name')!r}  org={p.get('org_id')}  owner={p.get('owner_id')}")
print(f"  emails={[e.get('value') for e in (p.get('emails') or [])]}")
cf = p.get("custom_fields") or {}
LI_KEYS = {"66f0af69bec838dc3f90bb3f16c7d6087d8dbb20": "linkedin_lh",
           "b59a7d0af178f3149381efd9a8476370b19ca3b5": "linkedin_profile"}
for k, label in LI_KEYS.items():
    print(f"  {label:<18} {json.dumps(cf.get(k))[:100]}")
other = {k: v for k, v in cf.items() if v and k not in LI_KEYS
         and isinstance(v, str) and "linkedin" in str(v).lower()}
for k, v in other.items():
    print(f"  (other li field) {k} = {v!r}")

print("\n=== what M7 actually sent (request URLs from the execution) ===")
d = n8n("/api/v1/executions/16703?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
for nm in ("M7 IF Email Present", "M7 Person Search URL", "M7 IF URL Found",
           "M7 Person Search Member", "M7 IF Member Verified", "M7 Slack Warn"):
    if nm not in rd:
        print(f"  {nm:<26} DID NOT RUN")
        continue
    run = rd[nm][0]
    try:
        out = run["data"]["main"][0][0]["json"]
    except Exception:
        out = {}
    blob = json.dumps(run, ensure_ascii=False)
    urls = re.findall(r'https://api\.pipedrive\.com[^"\\ ]{0,220}', blob)
    print(f"  --- {nm} ---")
    for u in dict.fromkeys(urls):
        print(f"      REQUEST {u[:210]}")
    if nm.startswith("M7 Person Search"):
        items = ((out.get("data") or {}) or {}).get("items")
        print(f"      RESULT items={len(items) if isinstance(items, list) else out.get('data')}")
        print(f"      raw: {json.dumps(out, ensure_ascii=False)[:220]}")
    elif "Warn" in nm:
        print(f"      posted: {json.dumps(out, ensure_ascii=False)[:200]}")

print("\n=== would a term search have found him? (what the resolver could have done) ===")
for term in ("https://www.linkedin.com/in/pii-7a798b9a", "linkedin.com/in/pii-7a798b9a",
             "philipcootey", "Person-9979a87c"):
    r = pd(f"/api/v2/persons/search?limit=5&term={urllib.parse.quote(term)}")
    items = ((r or {}).get("data") or {}).get("items") or []
    ids = [(i.get("item") or {}).get("id") for i in items]
    print(f"  term={term!r:<48} -> {len(items)} hit(s) {ids}")
