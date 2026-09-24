#!/usr/bin/env python3
"""CLASS SWEEP — every use of $getWorkflowStaticData across the estate, with concurrency exposure.

The Carla duplicate was not a WF-1 bug; it was a staticData bug that surfaced on WF-1. staticData is
persisted as a WHOLE OBJECT at execution end, so any two overlapping executions of the same workflow
lose one another's additions. The question for each store is therefore not "is it important" but
"can this workflow run twice at once".

Exposure is judged from the TRIGGER, which is what decides concurrency:
  webhook  -> HIGH   (providers fan several events into the same second; proven on WF-1)
  schedule -> LOW    (cron instances are serialised unless they overrun)
  manual   -> LOW
READ ONLY. Writes staticdata_sweep.json.
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


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


cur, wfs = None, []
while True:
    q = {"limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
    wfs += d.get("data") or []
    cur = d.get("nextCursor")
    if not cur:
        break
print(f"workflows in estate: {len(wfs)}\n")

KEYPAT = re.compile(r"(?:sd|SD|__sd|staticData)\s*(?:\.|\[['\"])\s*([A-Za-z_][\w]*)")
ASSIGN = re.compile(r"(?:sd|SD|__sd)\.(\w+)\s*=")
findings = []
for w in wfs:
    full = n8n(f"/api/v1/workflows/{w['id']}")
    blob = json.dumps(full, ensure_ascii=False)
    if "getWorkflowStaticData" not in blob:
        continue
    triggers = [n["type"].split(".")[-1] for n in full["nodes"]
                if any(t in n["type"].lower() for t in
                       ("webhook", "cron", "schedule", "trigger", "interval"))]
    kind = ("webhook" if any("webhook" in t.lower() for t in triggers)
            else ("schedule" if any(t.lower() in ("scheduletrigger", "cron", "interval")
                                    for t in triggers) else "other"))
    stores, writers = set(), set()
    for n in full["nodes"]:
        js = (n.get("parameters") or {}).get("jsCode") or ""
        pj = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
        src = js if js else pj
        if "getWorkflowStaticData" not in src and "sd." not in src:
            continue
        for m in KEYPAT.finditer(src):
            stores.add(m.group(1))
        for m in ASSIGN.finditer(src):
            writers.add((n["name"], m.group(1)))
    stores.discard("global")
    findings.append({"id": w["id"], "name": w["name"], "active": full.get("active"),
                     "trigger": kind, "triggers": sorted(set(triggers)),
                     "stores": sorted(stores),
                     "writer_nodes": sorted({f"{a} -> {b}" for a, b in writers})})

findings.sort(key=lambda f: (f["trigger"] != "webhook", not f["active"], f["name"]))
print(f"{'=' * 78}\nWORKFLOWS USING staticData: {len(findings)}\n{'=' * 78}")
for f in findings:
    risk = ("HIGH — webhook, parallel executions are routine"
            if f["trigger"] == "webhook" and f["active"]
            else ("LOW — scheduled, serialised unless a run overruns"
                  if f["trigger"] == "schedule" else "LOW"))
    print(f"\n{f['name'][:58]}  ({f['id']})  {'ACTIVE' if f['active'] else 'inactive'}")
    print(f"   trigger : {f['trigger']}  {f['triggers']}")
    print(f"   stores  : {f['stores'] or '(none parsed)'}")
    print(f"   writers : {f['writer_nodes'][:4] or '(none parsed)'}")
    print(f"   EXPOSURE: {risk}")

hi = [f for f in findings if f["trigger"] == "webhook" and f["active"]]
print(f"\n{'=' * 78}")
print(f"PORT CANDIDATES (active + webhook-triggered): {len(hi)}")
for f in hi:
    print(f"   {f['name'][:44]:<44} stores={f['stores']}")
json.dump(findings, open(os.path.join(HERE, "staticdata_sweep.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: staticdata_sweep.json")
