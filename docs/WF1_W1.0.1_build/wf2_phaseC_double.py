"""Phase C: build the WF-2 TEST DOUBLE from the shipped artifact by applying explicit deltas.

The double is derived mechanically from `WF-2 Smartlead Receiver - built.json`, never hand-edited,
so "what differs from production" is a list in one place rather than a diff nobody reads.

DELTAS (all of them):
  1  name                     -> marked DOUBLE / DELETE AFTER
  2  webhook path             -> its own path, so production traffic can never reach it
  3  WRITE_MODE               -> live   (the point of the exercise: real Pipedrive writes)
  4  slack channels           -> both -> ops channel, so no test alert lands in the team channel
  5  sl_api                   -> the in-n8n mock (no real prospect is ever written to)
  6  llm.base                 -> the in-n8n mock LLM
  7  SL node URLs             -> mock's STATIC paths, ids moved into the query string
  8  SL + LLM auth            -> stripped (the mock needs none; the Anthropic cred is deferred)
  9  classify_enabled         -> settable per run (the matrix runs it both ways)
 10  settings.saveData*       -> 'all', so every case can be asserted from execution truth

Everything else - all node code, all bodies, all wiring - is byte-identical to what ships.
"""
import argparse
import json
import sys
from pathlib import Path

DOUBLE_NAME = "WF-2 Smartlead Receiver - PHASE-C DOUBLE (DELETE AFTER)"
DOUBLE_PATH = "sl-c1-double"
OPS_CHANNEL = "C0B8GCVNR5W"

# ids ride in the query string because n8n Cloud 404s on ':param' webhook paths (probed)
SL_URL_REWRITES = {
    "SL Fetch Lead": "{{ '/leads?email=' + encodeURIComponent($('Normalize').item.json.lead.email) }}",
    "SL Message History": "{{ '/message-history?cid=' + $('Normalize').item.json.campaign_id"
                          " + '&lid=' + $('Normalize').item.json.sl_lead_id }}",
    "SL Category": "{{ '/category?cid=' + $('Normalize').item.json.campaign_id"
                   " + '&lid=' + $('Normalize').item.json.sl_lead_id }}",
    "SL Unsubscribe": "{{ '/unsubscribe?lid=' + $('Normalize').item.json.sl_lead_id }}",
    "U SL Unsubscribe": "{{ '/unsubscribe?lid=' + $('Normalize').item.json.sl_lead_id }}",
    "SL Forward Email": "{{ '/forward-email?cid=' + $('Normalize').item.json.campaign_id }}",
}
SL_BASE_EXPR = "={{ $('CONFIG').item.json.sl_api }}"


def build_double(src, n8n_base, classify_enabled, secret_hash=None):
    wf = json.loads(json.dumps(src))           # never mutate the shipped artifact
    deltas = []
    wf["name"] = DOUBLE_NAME
    deltas.append(f"name -> {DOUBLE_NAME}")

    byname = {n["name"]: n for n in wf["nodes"]}
    hook = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook")
    deltas.append(f"webhook path {hook['parameters']['path']} -> {DOUBLE_PATH}")
    hook["parameters"]["path"] = DOUBLE_PATH

    cfg = json.loads(byname["CONFIG"]["parameters"]["jsonOutput"])
    cfg["WRITE_MODE"] = "live"
    cfg["slack_channel_replies"] = OPS_CHANNEL
    cfg["slack_channel_ops"] = OPS_CHANNEL
    cfg["sl_api"] = f"{n8n_base}/webhook/slmock-c1"
    cfg["llm"]["base"] = f"{n8n_base}/webhook/llmmock-c1"
    cfg["classify_enabled"] = bool(classify_enabled)
    if secret_hash:
        # 11: webhook auth ARMED on the double so enforcement is proven live. Production ships
        # unarmed (accept + warn) until Nik sets the real hash - see the flip checklist.
        cfg["webhook_secret_sha256"] = secret_hash
    byname["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
    deltas += ["WRITE_MODE -> live", f"both slack channels -> {OPS_CHANNEL}",
               f"sl_api -> {cfg['sl_api']}", f"llm.base -> {cfg['llm']['base']}",
               f"classify_enabled -> {cfg['classify_enabled']}"]
    if secret_hash:
        deltas.append(f"webhook_secret_sha256 -> ARMED ({secret_hash[:12]}...)")

    for name, tail in SL_URL_REWRITES.items():
        n = byname[name]
        n["parameters"]["url"] = SL_BASE_EXPR + tail
        deltas.append(f"{name}: url -> mock static path")

    stripped = []
    for n in wf["nodes"]:
        if n["type"] != "n8n-nodes-base.httpRequest":
            continue
        url = str(n["parameters"].get("url", ""))
        if "sl_api" in url or "llm.base" in url:
            n["parameters"].pop("authentication", None)
            n["parameters"].pop("genericAuthType", None)
            n.pop("credentials", None)
            stripped.append(n["name"])
    deltas.append(f"auth stripped on {len(stripped)} mock-facing nodes: {', '.join(stripped)}")

    wf["settings"] = dict(wf.get("settings") or {})
    wf["settings"].update({"saveDataSuccessExecution": "all", "saveDataErrorExecution": "all",
                           "saveExecutionProgress": True, "executionOrder": "v1"})
    deltas.append("settings.saveData* -> all (execution truth for the matrix)")

    # the double must remain provably isolated from production
    assert hook["parameters"]["path"] != "{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}", "double must not share the prod path"
    assert cfg["slack_channel_replies"] == OPS_CHANNEL != "C07LTD8UT70"
    # the guard targets API hosts only. app.smartlead.ai is the master-inbox UI base used to build
    # a human-clickable deep link - it is never called by the workflow, so it must stay.
    assert "server.smartlead.ai" not in json.dumps(cfg), "no real Smartlead API endpoint may remain"
    assert cfg["sl_api"].startswith(n8n_base), "sl_api must point at the in-n8n mock"
    assert "api.anthropic.com" not in json.dumps(cfg), "no real Anthropic endpoint may remain"
    assert cfg["pd_api"] == "https://api.pipedrive.com", "Pipedrive stays REAL - that is the point"
    return wf, deltas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("--src", type=Path, default=Path("WF-2 Smartlead Receiver - built.json"))
    ap.add_argument("--n8n-base", required=True)
    ap.add_argument("--classify", default="true")
    ap.add_argument("--secret-hash", default=None,
                    help="arm webhook auth on the DOUBLE only (prod ships unarmed)")
    a = ap.parse_args()
    src = json.loads(a.src.read_text(encoding="utf-8"))
    wf, deltas = build_double(src, a.n8n_base.rstrip("/"), a.classify.lower() == "true",
                              a.secret_hash)
    payload = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    a.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"double built -> {a.output} ({len(wf['nodes'])} nodes)")
    for d in deltas:
        print(f"  delta: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
