#!/usr/bin/env python3
"""Person-58accf5a — duplicate HeyReach alert. Which gate let the second one through? READ ONLY."""
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


print("=== Carla in Pipedrive? (slug carla-garcia-keeper) ===")
for term in ("carla-garcia-keeper", "Person-58accf5a"):
    r = pd(f"/api/v2/persons/search?limit=5&term={urllib.parse.quote(term)}")
    items = ((r or {}).get("data") or {}).get("items") or []
    found = [((i.get("item") or {}).get("id"), (i.get("item") or {}).get("name"))
             for i in items[:3]]
    print(f"  {term!r:<26} -> {found}")

print("\n=== WF-1 executions mentioning her ===")
cur, pages, hits = None, 0, []
while pages < 8:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if not rd:
            continue
        if "carla-garcia-keeper" not in json.dumps(rd) and "Person-58accf5a" not in json.dumps(rd):
            continue
        hits.append((r, rd))
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break
print(f"  pages walked {pages}  executions {len(hits)}")
for r, rd in sorted(hits, key=lambda t: str(t[0].get("startedAt"))):
    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None
    nz = o("Normalize") or {}
    g = o("M7 Alert Gate") or {}
    b = o("M7 Build") or {}
    cs = o("M7 Critical Slack") or {}
    lc = o("M7 Labels Compute") or {}
    print(f"\n  exec {r['id']}  {r.get('startedAt')}  status={r.get('status')}")
    print(f"     event     : {nz.get('event')!r}")
    print(f"     campaign  : {str((nz.get('campaign') or {}).get('name'))[:46]!r} "
          f"id={(nz.get('campaign') or {}).get('id')}")
    print(f"     M7 Build  : person_id={b.get('person_id')!r} lead_id={str(b.get('lead_id'))[:12]!r}")
    print(f"     GATE      : should={g.get('__should_alert')} reason={g.get('__alert_reason')!r}")
    print(f"                 key={g.get('__alert_key')!r}  registry_size={g.get('__alert_registry_size')}")
    print(f"     manual?   : {g.get('__manual_thread')!r}")
    print(f"     posted    : ok={cs.get('ok')} ch={cs.get('channel')}")
    print(f"     labels    : lead={str(lc.get('lead_id'))[:12]!r} changed={lc.get('changed')}")
    print(f"     nodes     : {len(rd)}")

print("\n=== the live registry: is her key in it? ===")
wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
sd = wf.get("staticData") or {}
if isinstance(sd, str):
    sd = json.loads(sd)
reg = ((sd.get("global") or {}).get("__alerted_v1") or {})
print(f"  __alerted_v1 size: {len(reg)}")
carla = {k: v for k, v in reg.items() if "carla" in k.lower()}
print(f"  keys mentioning carla: {carla or 'NONE'}")
import collections
print(f"  key shapes: {dict(collections.Counter(k.split('|')[-1] for k in reg).most_common(6))}")
nulls = [k for k in reg if k.startswith("None") or k.startswith("null")]
print(f"  keys that look null-ish: {len(nulls)}")
