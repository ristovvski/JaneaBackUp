#!/usr/bin/env python3
"""Create WF-2R in n8n, INACTIVE. Verification is not optional and not inferred from the POST:
the workflow is re-read after creation and its live JSON compared field-by-field against what we
sent. A 200 from n8n has lied before."""
import json, os, ssl, sys, urllib.error, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SRC = "WF-2R Smartlead REPLY Reconciler - built.json"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY,
                                        "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:900]}")
        raise


wf = json.load(open(SRC, encoding="utf-8"))
existing = [w for w in (n8n("/api/v1/workflows?limit=100").get("data") or [])
            if w["name"] == wf["name"]]
if existing:
    print(f"already exists: {existing[0]['id']} active={existing[0].get('active')} - refusing to "
          "create a second copy")
    sys.exit(2)

# POST /workflows accepts only these keys
payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
           "settings": wf["settings"]}
created = n8n("/api/v1/workflows", "POST", payload)
wid = created.get("id")
print(f"created id={wid} active={created.get('active')}")

live = n8n(f"/api/v1/workflows/{wid}")
problems = []
if live.get("active") is not False:
    problems.append(f"active={live.get('active')} - must be created INACTIVE")
if len(live.get("nodes") or []) != len(wf["nodes"]):
    problems.append(f"node count {len(live.get('nodes') or [])} != {len(wf['nodes'])}")
sent = {n["name"]: n for n in wf["nodes"]}
got = {n["name"]: n for n in (live.get("nodes") or [])}
if set(sent) != set(got):
    problems.append(f"node name mismatch: missing={set(sent)-set(got)} extra={set(got)-set(sent)}")
for nm in sent.keys() & got.keys():
    a = (sent[nm].get("parameters") or {}).get("jsCode")
    b = (got[nm].get("parameters") or {}).get("jsCode")
    if a != b:
        problems.append(f"{nm}: jsCode differs after round-trip")
if json.dumps(live.get("connections"), sort_keys=True) != json.dumps(wf["connections"],
                                                                    sort_keys=True):
    problems.append("connections differ after round-trip")
livecfg = json.loads(got["CONFIG"]["parameters"]["jsonOutput"]) if "CONFIG" in got else {}
for k in ("max_per_run", "max_campaigns_per_cycle", "lookback_minutes",
          "ignore_replies_before", "wf2s_workflow_id"):
    exp = json.loads(sent["CONFIG"]["parameters"]["jsonOutput"])[k]
    if livecfg.get(k) != exp:
        problems.append(f"CONFIG.{k}: live {livecfg.get(k)!r} != built {exp!r}")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"\nworkflow id: {wid}")
print(f"  nodes      : {len(live.get('nodes') or [])}")
print(f"  active     : {live.get('active')}")
print(f"  versionId  : {live.get('versionId')}")
print(f"  floor      : {livecfg.get('ignore_replies_before')}")
print(f"  lookback   : {livecfg.get('lookback_minutes')} min")
print(f"  cap        : {livecfg.get('max_per_run')} / cycle, "
      f"{livecfg.get('max_campaigns_per_cycle')} campaign(s) per cycle")
sys.exit(1 if problems else 0)
