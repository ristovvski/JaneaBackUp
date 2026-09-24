#!/usr/bin/env python3
"""Import the DNC Phase-1 + STAGE-1-migration workflows into n8n via the public API, INACTIVE.
Mirrors WF1_W1.0.1_build/deploy_wf2r.py's verified pattern exactly: create, then re-GET and
diff field-by-field against what was sent. A 200 from n8n has lied before (that script's own words).
Read-only toward Data Tables -- this only creates WORKFLOW objects, never touches table schema.
"""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

FILES = [
    os.path.join(HERE, "subworkflows", "DNC__NormalizeIdentity__v1.json"),
    os.path.join(HERE, "subworkflows", "DNC__UpsertLedger__v1.json"),
    os.path.join(HERE, "subworkflows", "DNC__CheckLedger__v1.json"),
    os.path.join(HERE, "workflows", "heyreach_reply_to_dnc_ledger", "heyreach_reply_to_dnc_ledger.json"),
    os.path.join(HERE, "workflows", "dnc_expiry_job", "dnc_expiry_job.json"),
    os.path.join(HERE, "workflows", "smartlead_observability_readonly", "smartlead_observability_readonly.json"),
    os.path.join(HERE, "workflows", "dnc_check_service", "dnc_check_service.json"),
    os.path.join(HERE, "workflows", "dnc_s2_meeting_to_dnc", "dnc_s2_meeting_to_dnc.json"),
    os.path.join(HERE, "workflows", "dnc_s1_responded_to_dnc", "dnc_s1_responded_to_dnc.json"),
    os.path.join(HERE, "workflows", "dnc_escalation_detector", "dnc_escalation_detector.json"),
]


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY,
                                         "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


existing_all = n8n("/api/v1/workflows?limit=250").get("data") or []
existing_by_name = {w["name"]: w for w in existing_all}

results = []
for path in FILES:
    wf = json.load(open(path, encoding="utf-8"))
    name = wf["name"]
    if name in existing_by_name:
        e = existing_by_name[name]
        print(f"SKIP {name}: already exists id={e['id']} active={e.get('active')} -- refusing to duplicate")
        results.append({"name": name, "status": "skipped_exists", "id": e["id"]})
        continue

    payload = {"name": name, "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {})}
    try:
        created = n8n("/api/v1/workflows", "POST", payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:900]
        print(f"FAIL {name}: HTTP {e.code}: {body}")
        results.append({"name": name, "status": "create_failed", "http": e.code, "body": body})
        continue

    wid = created.get("id")
    live = n8n(f"/api/v1/workflows/{wid}")
    problems = []
    if live.get("active") is not False:
        problems.append(f"active={live.get('active')} -- must be created INACTIVE")
    if len(live.get("nodes") or []) != len(wf["nodes"]):
        problems.append(f"node count {len(live.get('nodes') or [])} != {len(wf['nodes'])}")
    sent_nodes = {n["name"]: n for n in wf["nodes"]}
    got_nodes = {n["name"]: n for n in (live.get("nodes") or [])}
    if set(sent_nodes) != set(got_nodes):
        problems.append(f"node name mismatch: missing={set(sent_nodes)-set(got_nodes)} extra={set(got_nodes)-set(sent_nodes)}")
    for nm in sent_nodes.keys() & got_nodes.keys():
        a = (sent_nodes[nm].get("parameters") or {}).get("jsCode")
        b = (got_nodes[nm].get("parameters") or {}).get("jsCode")
        if a is not None and a != b:
            problems.append(f"{nm}: jsCode differs after round-trip")
    if json.dumps(live.get("connections"), sort_keys=True) != json.dumps(wf["connections"], sort_keys=True):
        problems.append("connections differ after round-trip")

    status = "clean" if not problems else "problems"
    print(f"{'OK  ' if not problems else 'WARN'} {name}: id={wid} nodes={len(live.get('nodes') or [])} status={status}")
    for p in problems:
        print("       -", p)
    results.append({"name": name, "status": status, "id": wid, "problems": problems})

print("\n=== SUMMARY ===")
for r in results:
    print(json.dumps(r, indent=None))

any_bad = any(r["status"] not in ("clean", "skipped_exists") for r in results)
sys.exit(1 if any_bad else 0)
