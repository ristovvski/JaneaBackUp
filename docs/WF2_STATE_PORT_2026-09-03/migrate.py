# -*- coding: utf-8 -*-
"""Migrate WF-2's three staticData stores into the atomic claims table.

RUNS BEFORE THE CODE CHANGE, in the same window. The other order re-announces everybody in the gap.

NORMALISATION IS THE POINT, not just the move. The source registry holds mixed ISO strings and
epoch numbers; `Number(ISO)` is NaN and every comparison with NaN is false, so 4 of the 11
__alert_delivered entries could never be pruned - three of them real people who would have become
permanently un-re-alertable from ~2026-11-09. Every value is converted to ONE form here: an ISO
string in `claimed_at`. Anything that will not parse is REFUSED, not guessed.

Reads nothing it has not asserted:
  * staticData lives under `global`. Reading the top level shows zeros for every store and would
    migrate nothing while reporting success - that mistake was made once already, preparing this.
  * refuses to run on an empty `global`.
"""
import json, io, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("S2LIB", ""))
exec(open(os.path.join(os.environ["S2LIB"], "lib.py"), encoding="utf-8").read())

TABLE = "euyostwJYfJefItC"
WF2 = "jp7rum9Z0YDJkQWv"
FAMILY = {"wf2_seen": "wf2_seen", "__alert_delivered": "wf2_alert", "wf2_bounce_seen": "wf2_bounce"}


def to_iso(v):
    """One form out, or nothing. Never a guess."""
    if isinstance(v, bool):
        return None, "bool"
    if isinstance(v, (int, float)):
        n = float(v)
        if n <= 0 or n != n:
            return None, "non-positive/NaN number"
        # seconds vs milliseconds, decided by magnitude not by hope
        secs = n / 1000.0 if n > 1e11 else n
        if not (946684800 <= secs <= 4102444800):        # 2000-01-01 .. 2100-01-01
            return None, "epoch out of plausible range: %r" % v
        return (datetime.datetime.fromtimestamp(secs, datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.000Z")), "epoch"
    if isinstance(v, str) and v.strip():
        s = v.strip()
        try:
            d = datetime.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            try:
                d = datetime.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                return None, "unparsable string: %r" % v
        return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "iso"
    return None, "unhandled type %s" % type(v).__name__


def build_rows():
    wf = get("/api/v1/workflows/%s" % WF2)
    g = (wf.get("staticData") or {}).get("global")
    if not isinstance(g, dict) or not g:
        raise SystemExit("REFUSING: staticData.global is empty or missing - a top-level read would "
                         "have reported zeros and migrated nothing. Got: %r" % (g,))
    rows, shapes, refused = [], {"epoch": 0, "iso": 0}, []
    for store, family in FAMILY.items():
        src = g.get(store) or {}
        if not isinstance(src, dict):
            raise SystemExit("REFUSING: %s is %s, expected an object" % (store, type(src).__name__))
        for k, v in src.items():
            iso, how = to_iso(v)
            if iso is None:
                refused.append((store, k, how, repr(v)[:60]))
                continue
            shapes[how] = shapes.get(how, 0) + 1
            rows.append({"claim_key": family + "|" + str(k), "family": family,
                         "workflow": "WF-2", "event_time": iso, "claimed_at": iso,
                         "evidence": "migrated from staticData." + store + " on "
                                     + time.strftime("%Y-%m-%d")})
    return wf, g, rows, shapes, refused


UPSERT_WF = {
    "name": "TMP__wf2_state_migration",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": "tmp-wf2-migrate",
                        "responseMode": "lastNode", "options": {"rawBody": False}},
         "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
         "id": "mg-hook", "name": "Run",
         "webhookId": "b81c4f2e-6a37-4d95-9f10-2c8e7a5b3d64"},
        {"parameters": {"fieldToSplitOut": "body.rows", "options": {}},
         "type": "n8n-nodes-base.splitOut", "typeVersion": 1, "position": [200, 0],
         "id": "mg-split", "name": "Rows"},
        {"parameters": {"resource": "row", "operation": "upsert",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                        "matchType": "allConditions",
                        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                                    "keyValue": "={{ $json.claim_key }}"}]},
                        "columns": {"mappingMode": "defineBelow", "value": {
                            "claim_key": "={{ $json.claim_key }}",
                            "family": "={{ $json.family }}",
                            "workflow": "={{ $json.workflow }}",
                            "event_time": "={{ $json.event_time }}",
                            "claimed_at": "={{ $json.claimed_at }}",
                            "evidence": "={{ $json.evidence }}"}},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [400, 0],
         "id": "mg-upsert", "name": "Upsert", "retryOnFail": True,
         "onError": "continueRegularOutput"},
        {"parameters": {"jsCode":
            "const items = $input.all().map(i => i.json);\n"
            "const real = items.filter(r => r && typeof r.claim_key === 'string'\n"
            "                            && typeof r.claimed_at === 'string' && r.claimed_at);\n"
            "const byFam = {};\n"
            "real.forEach(r => { byFam[r.family] = (byFam[r.family] || 0) + 1; });\n"
            "return [{ json: { returned: items.length, real_rows: real.length, by_family: byFam,\n"
            "                  not_real: items.length - real.length } }];",
            "mode": "runOnceForAllItems"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 0],
         "id": "mg-sum", "name": "Summary"},
    ],
    "connections": {"Run": {"main": [[{"node": "Rows", "type": "main", "index": 0}]]},
                    "Rows": {"main": [[{"node": "Upsert", "type": "main", "index": 0}]]},
                    "Upsert": {"main": [[{"node": "Summary", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                 "callerPolicy": "workflowsFromSameOwner"},
}


def main():
    wf, g, rows, shapes, refused = build_rows()
    print("WF-2 versionId %s, staticData.global stores: %s"
          % (wf.get("versionId"), ", ".join("%s=%d" % (k, len(g.get(k) or {}))
                                            for k in FAMILY)))
    print("rows to write: %d  (from epoch %d, from ISO %d)"
          % (len(rows), shapes.get("epoch", 0), shapes.get("iso", 0)))
    for f in sorted(set(r["family"] for r in rows)):
        print("   %-12s %d" % (f, len([r for r in rows if r["family"] == f])))
    if refused:
        print("\nREFUSED (not migrated, reported instead):")
        for s, k, why, v in refused:
            print("   %-18s %-40s %s  %s" % (s, k[:40], why, v))
    if not rows:
        raise SystemExit("REFUSING: nothing to migrate")
    io.open(os.path.join(HERE, "migration_rows.json"), "w", encoding="utf-8").write(
        json.dumps(rows, ensure_ascii=False, indent=1))

    if "--dry-run" in sys.argv:
        print("\nDRY RUN - nothing written. rows saved to migration_rows.json")
        return
    r = create_wf(UPSERT_WF)
    if r.status_code >= 300:
        raise SystemExit("create failed %s %s" % (r.status_code, r.text[:300]))
    wid = r.json()["id"]
    try:
        activate(wid); time.sleep(3)
        resp = hook("tmp-wf2-migrate", {"rows": rows}, timeout=600)
        print("\nHTTP %s" % resp.status_code)
        j = resp.json(); j = j[0] if isinstance(j, list) else j
        print(json.dumps(j, ensure_ascii=False, indent=1))
        if j.get("real_rows") != len(rows):
            print("\n!! upsert returned %s real rows for %d sent - VERIFY BEFORE DEPLOYING CODE"
                  % (j.get("real_rows"), len(rows)))
    finally:
        deactivate(wid)
        print("temp workflow deleted:", _req("DELETE", "/api/v1/workflows/" + wid).status_code)


if __name__ == "__main__":
    main()
