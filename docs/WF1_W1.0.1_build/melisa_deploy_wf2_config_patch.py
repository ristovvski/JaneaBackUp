#!/usr/bin/env python3
"""Deploy the campaign_event_map fallback to WF-2's CONFIG node + Normalize node.
ROLLBACK-SAFE: exports the current full workflow definition to a timestamped file BEFORE any
change. Additive only - never overrides a successful bracket-parse, never touches any other key.
WF-2 is WRITE_MODE=shadow right now, so this patch cannot cause a live write on its own; it only
changes what shadow-mode WOULD compute/log, and what a future live flip would write.

WRITE_MODE=live required to actually PUT the change. Default is dry-run (prints the diff only).
"""
import json, os, ssl, sys, time
import urllib.request, urllib.parse

WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None
HERE = os.path.dirname(os.path.abspath(__file__))

CAMPAIGN_EVENT_MAP = {
    "3686193": {"hypothesis": "Events Visiting", "event_name": "Ai4 2026"},
    "3686187": {"hypothesis": "Events Visiting", "event_name": "Ai4 2026"},
    "3686184": {"hypothesis": "Events Visiting", "event_name": "Ai4 2026"},
    "3686181": {"hypothesis": "Events Visiting", "event_name": "Ai4 2026"},
}

FALLBACK_SNIPPET = """
// FALLBACK (2026-08-06): single-bracket email campaigns structurally can't carry a 2nd bracket
// for Event name. Consult an explicit CONFIG map before leaving it null. Never overrides a
// successful bracket-derived value - additive only.
const campIdStr = String(pick(b.campaign_id, b.campaign?.id, ld.campaign_id) ?? '');
const camFallback = (cfg.campaign_event_map || {})[campIdStr];
if (camFallback) {
  if (!hypothesis) hypothesis = camFallback.hypothesis ?? hypothesis;
  if (!event_name) event_name = camFallback.event_name ?? event_name;
}
"""

ANCHOR = ("if (groups.length >= 2) {\n"
          "    const ev = CANON_WS(groups[1]);\n"
          "    if (ev !== '' && ev.length <= 60 && !/\\[|\\]/.test(ev)) event_name = ev;\n"
          "  }\n"
          "}")


def n8n(path, method="GET", body=None, params=None):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json",
                                        **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return x.status, json.load(x)


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r} ({'LIVE - WILL DEPLOY' if live else 'dry run, no deploy'})")

    st, wf = n8n(f"/api/v1/workflows/{WF2}")
    if st != 200:
        sys.exit(f"ABORT: could not fetch WF-2, status {st}")

    # 1) ROLLBACK SNAPSHOT - always written, live or not
    ts = wf.get("updatedAt", "unknown").replace(":", "-")
    rollback_path = os.path.join(HERE, "wf1-release-evidence", f"WF2_ROLLBACK_before_config_patch_{ts}.json")
    with open(rollback_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False, default=str)
    print(f"rollback snapshot written: {rollback_path}")

    nodes = wf["nodes"]
    config_node = next(n for n in nodes if n["name"] == "CONFIG")
    normalize_node = next(n for n in nodes if n["name"] == "Normalize")

    # 2) patch CONFIG.jsonOutput - add campaign_event_map key (additive, parse-preserving)
    cfg_json = json.loads(config_node["parameters"]["jsonOutput"])
    if "campaign_event_map" in cfg_json:
        print("CONFIG already has campaign_event_map - checking it matches before touching anything")
        if cfg_json["campaign_event_map"] != CAMPAIGN_EVENT_MAP:
            sys.exit("ABORT: campaign_event_map already exists with DIFFERENT values - manual review needed")
        print("existing campaign_event_map matches exactly - no CONFIG change needed")
        cfg_changed = False
    else:
        cfg_json["campaign_event_map"] = CAMPAIGN_EVENT_MAP
        cfg_changed = True

    # 3) patch Normalize jsCode - insert fallback right after the two-bracket event_name block
    code = normalize_node["parameters"]["jsCode"]
    if "campIdStr" in code:
        print("Normalize already has the fallback snippet - skipping code change")
        code_changed = False
        new_code = code
    else:
        if ANCHOR not in code:
            sys.exit("ABORT: anchor text not found in Normalize code - code has changed since this "
                      "patch was written; re-derive the anchor before proceeding, do not guess.")
        new_code = code.replace(ANCHOR, ANCHOR + FALLBACK_SNIPPET, 1)
        code_changed = True

    if not cfg_changed and not code_changed:
        print("Nothing to deploy - both pieces already present and correct.")
        return

    print(f"\nchanges to apply: CONFIG add campaign_event_map={cfg_changed} | Normalize fallback={code_changed}")

    if not live:
        print("\n--- DRY RUN: would PUT the following node changes ---")
        if cfg_changed:
            print("CONFIG.jsonOutput would gain key 'campaign_event_map':")
            print(json.dumps(CAMPAIGN_EVENT_MAP, indent=2))
        if code_changed:
            print("\nNormalize.jsCode would gain (inserted after the two-bracket block):")
            print(FALLBACK_SNIPPET)
        return

    # 4) LIVE: apply changes to the in-memory node objects, PUT the whole workflow
    if cfg_changed:
        config_node["parameters"]["jsonOutput"] = json.dumps(cfg_json, indent=2)
    if code_changed:
        normalize_node["parameters"]["jsCode"] = new_code

    put_body = {"name": wf["name"], "nodes": nodes, "connections": wf["connections"],
                "settings": wf.get("settings", {})}
    st2, resp = n8n(f"/api/v1/workflows/{WF2}", method="PUT", body=put_body)
    print(f"\nPUT status: {st2}")
    if st2 >= 300:
        sys.exit(f"DEPLOY FAILED: {json.dumps(resp)[:400]}")

    # 5) VERIFY - fresh GET, confirm the diff landed and NOTHING else changed
    st3, wf_after = n8n(f"/api/v1/workflows/{WF2}")
    cfg_after = json.loads(next(n for n in wf_after["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    norm_after = next(n for n in wf_after["nodes"] if n["name"] == "Normalize")["parameters"]["jsCode"]
    assert cfg_after.get("campaign_event_map") == CAMPAIGN_EVENT_MAP, "CONFIG verify FAILED"
    assert "campIdStr" in norm_after, "Normalize verify FAILED"
    # sanity: node count unchanged (nothing added/removed)
    assert len(wf_after["nodes"]) == len(nodes), "NODE COUNT CHANGED - unexpected, investigate"
    print("VERIFY OK: campaign_event_map present, Normalize fallback present, node count unchanged.")
    print(f"\nROLLBACK: to revert, PUT the saved snapshot at {rollback_path} back to /api/v1/workflows/{WF2}")


if __name__ == "__main__":
    main()
