#!/usr/bin/env python3
"""Morning digest: add a Supabase-mirror status clause to the existing *DNC* line.

Before: "DNC active N (+A/-R 24h) · gate OK/FAILING Nms (F/C fail today)"
After:  same, plus " · Supabase mirror: N rows · age N min · reachable" (or "UNREACHABLE").

Inserted into the DNC line specifically (not a new top-level bullet) -- it's the same subject
(the DNC registry's health/reach) and the digest is already capped at 12 lines total.

Color folds into the SAME line's existing dot: red if Supabase is unreachable/paused (in addition
to the existing gate-FAILING red trigger), amber if reachable but the last sync is >60 min old (in
addition to the existing dnc-active-unreadable amber trigger), green otherwise.

Two new nodes inserted into the workflow's single linear chain, between "DNC Removed Agg" and
"Gate Monitor Last" (grouped with the other DNC-related steps): "Supabase Mirror Check" (row count
via Prefer:count=exact) and "Supabase Meta Check" (latest dnc_registry_meta row, any source, for
age) -- both read-only. A single "Supabase Mirror Agg" folds both into the running digest object.

Usage: python patch_morning_digest_supabase_mirror.py [--apply]
"""
import json
import os
import ssl
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

WID = "qJKfR602wV9yfFrj"
SUPABASE_URL = "https://icxrjwccqitqmpypwhie.supabase.co"
SUPABASE_CRED = {"id": "u6wyGnYC71Sr1KgT", "name": "Supabase account"}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


AGG_JS = (
    "// Supabase mirror status: row count (Prefer:count=exact -> Content-Range header) + age since\n"
    "// the latest dnc_registry_meta row (any sync source). A failed call on EITHER leg means\n"
    "// unreachable (paused free-tier project reads as a connection failure the same way a real\n"
    "// outage would) -- never guess a stale number when the read itself failed.\n"
    "const prev = $('DNC Removed Agg').first().json;\n"
    "const countResp = $('Supabase Mirror Check').first().json;\n"
    "const metaResp = $('Supabase Meta Check').first().json;\n"
    "const reachable = !(countResp && countResp.error) && !(metaResp && metaResp.error);\n"
    "let rows = null, ageMin = null;\n"
    "if (reachable) {\n"
    "  const header = countResp.headers && countResp.headers['content-range'];\n"
    "  rows = header ? (parseInt(header.split('/')[1], 10) || null) : null;\n"
    "  const metaRows = Array.isArray(metaResp.body) ? metaResp.body : [];\n"
    "  const last = metaRows[0];\n"
    "  if (last && last.last_sync_at) {\n"
    "    ageMin = Math.round((Date.now() - new Date(last.last_sync_at).getTime()) / 60000);\n"
    "  }\n"
    "}\n"
    "return [{ json: Object.assign({}, prev, {\n"
    "  supabase_reachable: reachable, supabase_rows: rows, supabase_age_min: ageMin,\n"
    "}) }];\n"
)

NEW_COUNT_CHECK = {
    "parameters": {
        "method": "GET",
        "url": "={{ '" + SUPABASE_URL + "/rest/v1/dnc_registry?select=id&limit=1' }}",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Prefer", "value": "count=exact"}]},
        "options": {"response": {"response": {"fullResponse": True}}},
    },
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [3600, 0],
    "id": "digest-supabase-mirror-check", "name": "Supabase Mirror Check",
    "credentials": {"supabaseApi": SUPABASE_CRED}, "onError": "continueErrorOutput",
}
NEW_META_CHECK = {
    "parameters": {
        "method": "GET",
        "url": "={{ '" + SUPABASE_URL + "/rest/v1/dnc_registry_meta?select=last_sync_at&order=last_sync_at.desc&limit=1' }}",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
        "options": {"response": {"response": {"fullResponse": True}}},
    },
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [3720, 0],
    "id": "digest-supabase-meta-check", "name": "Supabase Meta Check",
    "credentials": {"supabaseApi": SUPABASE_CRED}, "onError": "continueErrorOutput",
}
NEW_AGG = {
    "parameters": {"jsCode": AGG_JS, "mode": "runOnceForAllItems"},
    "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [3840, 0],
    "id": "digest-supabase-mirror-agg", "name": "Supabase Mirror Agg",
}

OLD_DNC = """  const st = d.__dnc_active_readable === false ? 'amber'
           : (d.__gate_readable && d.gate_healthy === false) ? 'red' : 'green';
  let line = dot(st) + ' *DNC* active ' + num(d.dnc_active)
    + ' (+' + num(d.dnc_added_24h) + ' / -' + num(d.dnc_removed_24h) + ' 24h)'
    + ' · gate ' + (d.__gate_readable ? (d.gate_healthy ? 'OK' : 'FAILING') : 'unreadable')
    + ' ' + num(d.gate_latency_ms) + 'ms'
    + ' (' + num(d.gate_failures_today) + '/' + num(d.gate_checks_today) + ' fail today)';
  if (d.__gate_readable && d.gate_healthy === false) {
    line += ' — <' + base + '/workflow/' + cfg.gate_monitor_id + '/executions|gate monitor>';
  }
  L.push(line);"""

NEW_DNC = """  // Supabase mirror folded into the same line/dot 2026-09-14: same subject (DNC registry
  // health/reach), and the digest is capped at 12 lines total -- not worth a new bullet.
  const supBad = d.supabase_reachable === false;
  const supStale = d.supabase_reachable === true && (d.supabase_age_min === null || d.supabase_age_min > 60);
  const st = (supBad || (d.__gate_readable && d.gate_healthy === false)) ? 'red'
           : (d.__dnc_active_readable === false || supStale) ? 'amber' : 'green';
  let line = dot(st) + ' *DNC* active ' + num(d.dnc_active)
    + ' (+' + num(d.dnc_added_24h) + ' / -' + num(d.dnc_removed_24h) + ' 24h)'
    + ' · gate ' + (d.__gate_readable ? (d.gate_healthy ? 'OK' : 'FAILING') : 'unreadable')
    + ' ' + num(d.gate_latency_ms) + 'ms'
    + ' (' + num(d.gate_failures_today) + '/' + num(d.gate_checks_today) + ' fail today)'
    + ' · Supabase mirror: ' + (d.supabase_reachable
        ? (num(d.supabase_rows) + ' rows · age ' + num(d.supabase_age_min) + ' min · reachable')
        : 'UNREACHABLE');
  if (d.__gate_readable && d.gate_healthy === false) {
    line += ' — <' + base + '/workflow/' + cfg.gate_monitor_id + '/executions|gate monitor>';
  }
  L.push(line);"""


def main():
    live = n8n(f"/api/v1/workflows/{WID}")
    with open(os.path.join(HERE, "backups_dnc_morning_digest__pre_supabase_mirror.json"), "w", encoding="utf-8") as f:
        json.dump(live, f, ensure_ascii=False, indent=1)

    wf = json.loads(json.dumps(live))  # deep copy

    def node(nm):
        for n in wf["nodes"]:
            if n["name"] == nm:
                return n
        raise KeyError(nm)

    # re-runnable: drop any prior copy of the new nodes before re-adding (same guard as
    # patch_morning_digest.py's own precedent -- a re-run must not double-insert).
    drop = {NEW_COUNT_CHECK["name"], NEW_META_CHECK["name"], NEW_AGG["name"]}
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in drop]
    wf["nodes"] += [NEW_COUNT_CHECK, NEW_META_CHECK, NEW_AGG]

    # splice into the linear chain: DNC Removed Agg -> Supabase Mirror Check -> Supabase Meta
    # Check -> Supabase Mirror Agg -> Gate Monitor Last (was: DNC Removed Agg -> Gate Monitor Last)
    assert node("DNC Removed Agg"), "DNC Removed Agg not found -- refusing to splice blind"
    assert node("Gate Monitor Last"), "Gate Monitor Last not found -- refusing to splice blind"
    wf["connections"]["DNC Removed Agg"] = {"main": [[{"node": "Supabase Mirror Check", "type": "main", "index": 0}]]}
    wf["connections"]["Supabase Mirror Check"] = {"main": [[{"node": "Supabase Meta Check", "type": "main", "index": 0}],
                                                             [{"node": "Supabase Meta Check", "type": "main", "index": 0}]]}
    wf["connections"]["Supabase Meta Check"] = {"main": [[{"node": "Supabase Mirror Agg", "type": "main", "index": 0}],
                                                           [{"node": "Supabase Mirror Agg", "type": "main", "index": 0}]]}
    wf["connections"]["Supabase Mirror Agg"] = {"main": [[{"node": "Gate Monitor Last", "type": "main", "index": 0}]]}

    comp = node("Compose")
    js = comp["parameters"]["jsCode"]
    already = "Supabase mirror" in js
    if not already:
        assert OLD_DNC in js, "Compose DNC block is neither the original nor the patched version -- refusing to patch blind"
        js = js.replace(OLD_DNC, NEW_DNC)
    else:
        print("Compose already patched -- leaving it as is")
    comp["parameters"]["jsCode"] = js

    # integrity: no dangling edges, no duplicate node names
    names = {n["name"] for n in wf["nodes"]}
    for s, v in wf["connections"].items():
        assert s in names, "dangling source " + s
        for br in (v.get("main") or []):
            for t in br:
                assert t["node"] in names, "dangling target " + t["node"]
    from collections import Counter
    dupes = [k for k, v in Counter(n["name"] for n in wf["nodes"]).items() if v > 1]
    assert not dupes, "duplicate node names: " + str(dupes)

    with open(os.path.join(HERE, "patched_dnc_morning_digest.json"), "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=1)
    print(f"nodes {len(live['nodes'])} -> {len(wf['nodes'])}  (+Supabase Mirror Check, Supabase Meta Check, Supabase Mirror Agg)")
    print("Compose: DNC line now includes 'Supabase mirror: N rows · age N min · reachable'")

    if "--apply" in sys.argv:
        was_active = live.get("active", False)
        n8n(f"/api/v1/workflows/{WID}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{WID}", "PUT",
            {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": wf["settings"]})
        if was_active:
            n8n(f"/api/v1/workflows/{WID}/activate", "POST", {})
        b = n8n(f"/api/v1/workflows/{WID}")
        print(f"readback: active={b.get('active')} nodes={len(b['nodes'])}")


if __name__ == "__main__":
    main()
