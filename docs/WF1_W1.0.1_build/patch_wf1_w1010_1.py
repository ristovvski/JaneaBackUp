#!/usr/bin/env python3
"""W1.0.10.1 micro-patch: route reply alerts back to Nik's (ops) channel — temporary.

Context: W1.0.10 (channel split) was built but NOT deployed (its pre-deploy gate found the bot
was channel_not_found on C07LTD8UT70). This release ships the W1.0.10 split ARCHITECTURE (keys +
node repoints) but points replies back to ops so nothing changes visibly and reply alerts don't
duplicate the team's Zap #4 messages. Flipping back later = set slack_channel_replies to
"C07LTD8UT70" (after confirming bot membership) — a CONFIG one-liner; nodes already read the key.

Change: CONFIG.slack_channel_replies -> "C0B8GCVNR5W" (== ops). Architecture untouched:
M7 Critical Slack + M7 Slack Warn still read slack_channel_replies; the 5 ops/warn/error nodes read
slack_channel_ops; slack_channel alias stays ops. Input: W1.0.10 patched JSON. Deterministic,
no network. Node count unchanged (93).
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

OPS = "C0B8GCVNR5W"


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if "slack_channel_replies" not in cfg or "slack_channel_ops" not in cfg:
        raise ValueError("input is not a W1.0.10 (split) artifact — missing channel keys")
    if cfg["slack_channel_replies"] != "C07LTD8UT70":
        raise ValueError(f"unexpected slack_channel_replies {cfg['slack_channel_replies']!r} (expected the team channel to flip from)")
    cfg["slack_channel_replies"] = OPS  # temporary: replies back to ops
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2)
    w.pop("pinData", None)
    w["active"] = False
    return w


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("slack_channel_replies") != OPS: e.append("slack_channel_replies must be ops (C0B8GCVNR5W)")
    if cfg.get("slack_channel_ops") != OPS: e.append("slack_channel_ops must be C0B8GCVNR5W")
    if cfg.get("slack_channel") != OPS: e.append("slack_channel alias must be ops")
    reply = {"M7 Critical Slack", "M7 Slack Warn"}
    ops = {"M7 No Lead Warn", "M5 Slack Warn", "M6 Slack Warn", "M6 Message First Warn", "Lead Resp Invalid"}
    for n in w["nodes"]:
        if n["type"] != "n8n-nodes-base.slack": continue
        v = n["parameters"]["channelId"]["value"]
        if not v.startswith("={{"): e.append(f"{n['name']}: literal channel id")
        if n["name"] in reply and "slack_channel_replies" not in v: e.append(f"{n['name']}: must keep reading slack_channel_replies")
        if n["name"] in ops and "slack_channel_ops" not in v: e.append(f"{n['name']}: must keep reading slack_channel_ops")
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
    print(f"W1.0.10.1 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
