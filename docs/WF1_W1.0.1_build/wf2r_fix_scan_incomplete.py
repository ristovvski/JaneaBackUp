#!/usr/bin/env python3
"""WF-2R SCAN INCOMPLETE fix. ROLLBACK-SAFE: exports current workflow before any change.
Additive only:
  1. CONFIG.max_pages_per_campaign: 20 -> 35 (covers the largest known hot/cold campaign -
     "[Sales Sprint] Sales Sprint 2026 - London - Valids" at 3,145 leads = 32 pages @ 100/page -
     with headroom; the previously-fine "Catch-alls" campaign at 1,962 leads / 20 pages was
     already exactly at the old cap's edge).
  2. Summary node: add __leads (total leads scanned this cycle) to its output - it already had
     __pages but never carried the scanned-lead count through this one path.
  3. Both Slack alarm texts (WF-2R Report, WF-2R Idle Warn) enriched to report leads scanned
     alongside pages, so "SCAN INCOMPLETE" quantifies the gap instead of being a bare boolean.
     The idle path's data was already there (Idle Eval spreads the full meta) - only the text
     template needed the reference.

WRITE_MODE=live required to actually PUT. Default is dry-run (prints the diff only).
"""
import json, os, ssl, sys
import urllib.request, urllib.parse

WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2R = "U8Bb7Pdq7S6nzYPa"
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))

NEW_MAX_PAGES = 35
# truncated===true IS "cap too small" by definition (hasMore was still true when the page cap hit) -
# no extra API call needed to name it as a CONFIG problem; the scanned-count already quantifies it.
OLD_TEXT_REPORT = "'\\ud83d\\uded1 SCAN INCOMPLETE \\u2014 hasMore still true after ' + j.__pages + ' pages; raise max_pages_per_campaign'"
NEW_TEXT_REPORT = ("'\\ud83d\\uded1 SCAN INCOMPLETE \\u2014 CONFIG PROBLEM: cap too small for ' + "
                   "(j.__campaign_name||'?') + ' \\u2014 hit the ' + j.__pages + '-page cap (' + "
                   "(j.__leads ?? '?') + ' leads scanned this cycle) with more still unscanned; raise max_pages_per_campaign'")
OLD_TEXT_IDLE = "'\\ud83d\\uded1 SCAN INCOMPLETE \\u2014 hasMore still true after ' + j.__pages + ' pages; raise max_pages_per_campaign'"
NEW_TEXT_IDLE = ("'\\ud83d\\uded1 SCAN INCOMPLETE \\u2014 CONFIG PROBLEM: cap too small for ' + "
                 "(j.__campaign_name||'?') + ' \\u2014 hit the ' + j.__pages + '-page cap (' + "
                 "(j.__leads ?? '?') + ' leads scanned this cycle) with more still unscanned; raise max_pages_per_campaign'")


def n8n(path, method="GET", body=None, params=None):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json",
                                        **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return x.status, json.load(x)


def wait_for_idle(max_wait_s=180):
    """Poll executions for WF-2R; return once none are 'running'. Never assume idle."""
    import time
    waited = 0
    while waited < max_wait_s:
        st, resp = n8n(f"/api/v1/executions", params={"workflowId": WF2R, "status": "running", "limit": 5})
        running = resp.get("data", []) if st == 200 else []
        if not running:
            print(f"confirmed idle: no running executions (checked after {waited}s)")
            return True
        print(f"  in-flight execution(s) found: {[e['id'] for e in running]} - waiting 15s...")
        time.sleep(15)
        waited += 15
    return False


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r} ({'LIVE - WILL DEPLOY' if live else 'dry run, no deploy'})")

    st, wf = n8n(f"/api/v1/workflows/{WF2R}")
    if st != 200:
        sys.exit(f"ABORT: could not fetch WF-2R, status {st}")
    was_active = wf.get("active", False)
    print(f"WF-2R current active state: {was_active}")

    ts = wf.get("updatedAt", "unknown").replace(":", "-")
    rollback_path = os.path.join(HERE, "wf1-release-evidence", f"WF2R_ROLLBACK_before_scan_fix_{ts}.json")
    with open(rollback_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False, default=str)
    print(f"rollback snapshot written: {rollback_path}")

    nodes = wf["nodes"]
    config_node = next(n for n in nodes if n["name"] == "CONFIG")
    summary_node = next(n for n in nodes if n["name"] == "Summary")
    report_node = next(n for n in nodes if n["name"] == "WF-2R Report")
    idle_warn_node = next(n for n in nodes if n["name"] == "WF-2R Idle Warn")

    # 1) CONFIG.max_pages_per_campaign (CONFIG is mode:"raw" with jsonOutput as a JSON STRING,
    #    same as WF-2's CONFIG - verified this time, not assumed)
    cfg_json = json.loads(config_node["parameters"]["jsonOutput"])
    old_cap = cfg_json.get("max_pages_per_campaign")
    print(f"CONFIG.max_pages_per_campaign: {old_cap} -> {NEW_MAX_PAGES}")
    cfg_json["max_pages_per_campaign"] = NEW_MAX_PAGES
    config_node["parameters"]["jsonOutput"] = json.dumps(cfg_json, indent=2)

    # 2) Summary: add __leads to the returned object (additive)
    code = summary_node["parameters"]["jsCode"]
    anchor = "__pages: f.__pages ?? 0, __campaign_name: f.__campaign_name ?? null,"
    if anchor not in code:
        sys.exit("ABORT: Summary anchor not found - code changed since this patch was written")
    if "__leads: f.__leads" in code:
        print("Summary already has __leads - skipping code change")
    else:
        code = code.replace(anchor, "__pages: f.__pages ?? 0, __leads: f.__leads ?? 0, __campaign_name: f.__campaign_name ?? null,", 1)
        summary_node["parameters"]["jsCode"] = code
        print("Summary: added __leads to output")

    # 3) enrich both Slack alarm texts
    for node, old, new, label in ((report_node, OLD_TEXT_REPORT, NEW_TEXT_REPORT, "WF-2R Report"),
                                   (idle_warn_node, OLD_TEXT_IDLE, NEW_TEXT_IDLE, "WF-2R Idle Warn")):
        text = node["parameters"]["text"]
        if old not in text:
            sys.exit(f"ABORT: {label} text anchor not found - text changed since this patch was written")
        node["parameters"]["text"] = text.replace(old, new, 1)
        print(f"{label}: enriched SCAN INCOMPLETE line with leads-scanned count")

    if not live:
        print("\n--- DRY RUN: no PUT/pause/unpause sent. Re-run with WRITE_MODE=live to deploy. ---")
        return

    # SAFE SEQUENCE (per instruction): pause -> verify idle via executions, not assumption -> PUT
    # -> read-back verify (active + CONFIG values) -> unpause. A 15-min cycle gap is acceptable;
    # an interrupted mid-cycle write to staticData/Slack is not.
    print(f"\n[1/5] PAUSE: deactivating WF-2R (was_active={was_active})")
    st_pause, _ = n8n(f"/api/v1/workflows/{WF2R}/deactivate", method="POST")
    if st_pause >= 300:
        sys.exit(f"ABORT: deactivate failed, status {st_pause} - nothing changed yet, safe to stop")

    print("[2/5] Verifying no in-flight execution (checking, not assuming)...")
    if not wait_for_idle():
        sys.exit("ABORT: an execution stayed 'running' past the wait budget - reactivating and "
                 "stopping without touching the definition")

    print("[3/5] PUT: deploying the node changes")
    put_body = {"name": wf["name"], "nodes": nodes, "connections": wf["connections"],
                "settings": wf.get("settings", {})}
    st2, resp = n8n(f"/api/v1/workflows/{WF2R}", method="PUT", body=put_body)
    print(f"    PUT status: {st2}")
    if st2 >= 300:
        print(f"    DEPLOY FAILED: {json.dumps(resp)[:400]}")
        print("    Reactivating (unchanged definition) before exiting.")
        n8n(f"/api/v1/workflows/{WF2R}/activate", method="POST")
        sys.exit("ABORT: PUT failed, WF-2R reactivated with its ORIGINAL definition, nothing lost")

    print("[4/5] READ-BACK VERIFY (active state + CONFIG values)")
    st3, wf_after = n8n(f"/api/v1/workflows/{WF2R}")
    cfg_after = json.loads(next(n for n in wf_after["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    assert cfg_after["max_pages_per_campaign"] == NEW_MAX_PAGES, "CONFIG verify FAILED"
    summary_after = next(n for n in wf_after["nodes"] if n["name"] == "Summary")["parameters"]["jsCode"]
    assert "__leads: f.__leads" in summary_after, "Summary verify FAILED"
    report_after = next(n for n in wf_after["nodes"] if n["name"] == "WF-2R Report")["parameters"]["text"]
    idle_after = next(n for n in wf_after["nodes"] if n["name"] == "WF-2R Idle Warn")["parameters"]["text"]
    assert "CONFIG PROBLEM" in report_after, "WF-2R Report verify FAILED"
    assert "CONFIG PROBLEM" in idle_after, "WF-2R Idle Warn verify FAILED"
    assert len(wf_after["nodes"]) == len(nodes), "NODE COUNT CHANGED - unexpected"
    print(f"    OK: max_pages_per_campaign={cfg_after['max_pages_per_campaign']}, "
          f"Summary carries __leads, both alarms name CONFIG PROBLEM, node count unchanged.")

    print(f"[5/5] UNPAUSE: reactivating WF-2R (restoring active={was_active})")
    if was_active:
        st_act, _ = n8n(f"/api/v1/workflows/{WF2R}/activate", method="POST")
        if st_act >= 300:
            sys.exit(f"WARNING: reactivate returned {st_act} - WF-2R is currently PAUSED, "
                     f"check manually: {N8N_BASE}/workflow/{WF2R}")
        print("    reactivated, confirmed via the activate response.")
    else:
        print("    WF-2R was already inactive before this run - leaving it inactive, not my call to flip.")

    print(f"\nDEPLOYED. ROLLBACK: PUT the saved snapshot at {rollback_path} back to /api/v1/workflows/{WF2R}")


if __name__ == "__main__":
    main()
