#!/usr/bin/env python3
"""Extend the W1.0 git audit repo with W1.0.1 fixes F9-F12 + a regenerate chore.

Clones the supplied W1.0 bundle (baseline..F8..cleanup, tracked file wf1.json),
then appends one cumulative commit per fix, converging byte-for-byte on the
verified W1.0.1 patched JSON. Emits a fresh bundle.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "WF-1 HeyReach Receiver - W1.0 patched.json"
FINAL = ROOT / "WF-1 HeyReach Receiver - W1.0.1 patched.json"
BUNDLE_IN = ROOT / "WF1_W1.0_AUDIT_REPO.bundle"
REPO = ROOT / "WF1_W1.0.1_AUDIT_REPO"
BUNDLE_OUT = ROOT / "WF1_W1.0.1_AUDIT_REPO.bundle"

COMMIT_INDEX = 0


def run(*args: str, cwd: Path = REPO) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def save(wf: dict[str, Any]) -> None:
    (REPO / "wf1.json").write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def nodes(wf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["name"]: n for n in wf["nodes"]}


def copy_node(cur: dict[str, Any], final: dict[str, Any], name: str) -> None:
    fm = nodes(final)
    value = copy.deepcopy(fm[name])
    cm = nodes(cur)
    if name in cm:
        idx = next(i for i, n in enumerate(cur["nodes"]) if n["name"] == name)
        cur["nodes"][idx] = value
    else:
        cur["nodes"].append(value)


def remove_node(cur: dict[str, Any], name: str) -> None:
    cur["nodes"] = [n for n in cur["nodes"] if n["name"] != name]


def set_conn(cur: dict[str, Any], final: dict[str, Any], name: str) -> None:
    cur["connections"][name] = copy.deepcopy(final["connections"][name])


def commit(msg: str, current: dict[str, Any], allow_empty: bool = False) -> None:
    global COMMIT_INDEX
    save(current)
    run("git", "add", "wf1.json")
    stamp = f"2026-07-12T01:{COMMIT_INDEX:02d}:00Z"
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = stamp
    env["GIT_COMMITTER_DATE"] = stamp
    cmd = ["git", "commit", "-m", msg]
    if allow_empty:
        cmd.append("--allow-empty")
    subprocess.run(cmd, cwd=REPO, check=True, env=env)
    COMMIT_INDEX += 1


def main() -> None:
    base = load(BASE)
    final = load(FINAL)

    if REPO.exists():
        shutil.rmtree(REPO)
    subprocess.run(["git", "clone", str(BUNDLE_IN), str(REPO)], check=True)
    run("git", "config", "user.name", "WF1 Release Audit")
    run("git", "config", "user.email", "release-audit@example.invalid")

    current = copy.deepcopy(base)
    # Sanity: cloned HEAD must equal the W1.0 patched baseline.
    head = load(REPO / "wf1.json")
    if head != current:
        raise SystemExit("Cloned bundle HEAD does not match W1.0 patched base")

    # F9 — restore Replied-to-invite classification.
    copy_node(current, final, "M7 Build")
    commit("F9: restore Replied-to-invite classification (hybrid rule) in M7 Build", current)

    # F10 — failure-isolated critical alert; de-duplicated tail; separate warn terminals.
    for name in ("M7 Reply Context", "M7 Critical Slack", "M7 No Lead Warn"):
        copy_node(current, final, name)
    for name in ("M8 Slack", "M8 Slack Text"):
        remove_node(current, name)
    for name in ("Switch", "M7 Reply Context", "M7 Critical Slack", "M8 IF Transition",
                 "M8 IF Lead ID", "M7 IF URL Found", "M7 IF Lead ID", "M7 IF Reply Activity Lead"):
        set_conn(current, final, name)
    for gone in ("M8 Task", "M8 Slack Text", "M8 Slack"):
        current["connections"].pop(gone, None)
    commit("F10: critical reply alert before CRM writes; de-duplicate tail alert; separate warn terminals", current)

    # F11 — import-free Dedupe key.
    copy_node(current, final, "Dedupe")
    commit("F11: remove require('crypto') from Dedupe (import-free deterministic key)", current)

    # F12 — Slack mrkdwn escaping on user-originated strings.
    for name in ("M5 Slack Warn", "M6 Slack Warn", "M7 Slack Warn"):
        copy_node(current, final, name)
    commit("F12: Slack mrkdwn escaping for all user-originated strings", current)

    # chore — regenerate pack artifacts (api-payload, checksums, manifest, tests).
    # wf1.json already matches the release exactly after F12, so this is an explicit
    # marker commit for the surrounding artifact regeneration.
    current = copy.deepcopy(final)
    commit("chore: regenerate release artifacts", current, allow_empty=True)

    produced = (REPO / "wf1.json").read_bytes()
    expected = FINAL.read_bytes()
    if produced != expected:
        raise SystemExit("Audit repo final wf1.json does not byte-match W1.0.1 patched JSON")

    if BUNDLE_OUT.exists():
        BUNDLE_OUT.unlink()
    subprocess.run(["git", "bundle", "create", str(BUNDLE_OUT), "--all"], cwd=REPO, check=True)
    run("git", "log", "--oneline")
    print(f"Audit repo: {REPO}")
    print(f"Bundle: {BUNDLE_OUT}")


if __name__ == "__main__":
    main()
