#!/usr/bin/env python3
"""W1.0.10 micro-patch: split alert channels.

Nik's decision: prospect-reply alerts go to the TEAM channel; ops/errors stay in Nik's channel.
- CONFIG: add slack_channel_replies="C07LTD8UT70" (team) + slack_channel_ops="C0B8GCVNR5W" (ops).
  Keep slack_channel="C0B8GCVNR5W" as an alias of ops (for any external reference).
- Reply-posting nodes -> slack_channel_replies: M7 Critical Slack, M7 Slack Warn.
- Ops/warn/error nodes -> slack_channel_ops: M7 No Lead Warn, M5 Slack Warn, M6 Slack Warn,
  M6 Message First Warn, Lead Resp Invalid.
- WF-ERR workflow (separate, BbrXPABgOaaTJjD6) uses a literal C0B8GCVNR5W already — untouched.
All channels remain CONFIG expressions (no literal ids in WF-1 nodes). Input: W1.0.9 patched JSON.
Deterministic, no network. Node count unchanged (93).
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

REPLIES = "C07LTD8UT70"
OPS = "C0B8GCVNR5W"
REPLY_NODES = ["M7 Critical Slack", "M7 Slack Warn"]
OPS_NODES = ["M7 No Lead Warn", "M5 Slack Warn", "M6 Slack Warn", "M6 Message First Warn", "Lead Resp Invalid"]
OLD_VAL = "={{ $('CONFIG').item.json.slack_channel }}"
REPLIES_VAL = "={{ $('CONFIG').item.json.slack_channel_replies }}"
OPS_VAL = "={{ $('CONFIG').item.json.slack_channel_ops }}"


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}

    # CONFIG
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if "slack_channel_replies" in cfg or "slack_channel_ops" in cfg:
        raise ValueError("CONFIG already has W1.0.10 channel keys")
    cfg["slack_channel_replies"] = REPLIES
    cfg["slack_channel_ops"] = OPS
    cfg["slack_channel"] = OPS  # keep as alias of ops (was already OPS)
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2)

    def repoint(name, new_val):
        node = bn[name]["parameters"]["channelId"]
        if node.get("value") != OLD_VAL:
            raise ValueError(f"{name}: channelId.value not the expected slack_channel expr (got {node.get('value')!r})")
        node["value"] = new_val

    for n in REPLY_NODES:
        repoint(n, REPLIES_VAL)
    for n in OPS_NODES:
        repoint(n, OPS_VAL)

    w.pop("pinData", None)
    w["active"] = False
    return w


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("slack_channel_replies") != REPLIES: e.append("CONFIG.slack_channel_replies wrong/missing")
    if cfg.get("slack_channel_ops") != OPS: e.append("CONFIG.slack_channel_ops wrong/missing")
    if cfg.get("slack_channel") != OPS: e.append("CONFIG.slack_channel alias must == ops")
    slack = [n for n in w["nodes"] if n["type"] == "n8n-nodes-base.slack"]
    for n in slack:
        val = n["parameters"]["channelId"]["value"]
        if not val.startswith("={{"):
            e.append(f"{n['name']}: literal channel id (must be a CONFIG expression): {val!r}")
        if n["name"] in REPLY_NODES and "slack_channel_replies" not in val:
            e.append(f"{n['name']}: must reference slack_channel_replies")
        if n["name"] in OPS_NODES and "slack_channel_ops" not in val:
            e.append(f"{n['name']}: must reference slack_channel_ops")
    # no WF-1 slack node should still reference the bare alias
    for n in slack:
        if n["parameters"]["channelId"]["value"] == OLD_VAL:
            e.append(f"{n['name']}: still on bare slack_channel alias")
    if w.get("active") is not False: e.append("not inactive")
    if "pinData" in w: e.append("pinData present")
    if len(w["nodes"]) != 93: e.append(f"expected 93 nodes, got {len(w['nodes'])}")
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path); ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    a = ap.parse_args()
    wf = json.loads(a.input.read_text(encoding="utf-8"))
    patched = apply_patch(wf)
    errs = validate(patched)
    if errs:
        for x in errs: print(f"ERROR: {x}", file=sys.stderr)
        return 1
    a.output.write_bytes((json.dumps(patched, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if a.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        a.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"W1.0.10 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
