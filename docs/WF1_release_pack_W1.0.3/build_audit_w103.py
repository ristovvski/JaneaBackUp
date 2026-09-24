#!/usr/bin/env python3
"""Append W1.0.3 commits R1..R6 to the audit repo, converging byte-exact on the release.

Starts from the existing bundle (HEAD = F13 / W1.0.2 wf1.json) and applies one
cumulative commit per patch by copying the affected nodes/connections from the
verified W1.0.3 final. R4 is cross-cutting (strip empty custom fields); its
per-node strips ride with the node each patch first rewrites, and the R4 commit
carries the remaining one (M7 Build).
"""
from __future__ import annotations
import copy, json, os, shutil, subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "WF-1 HeyReach Receiver - W1.0.2 patched.json"
FINAL = ROOT / "WF-1 HeyReach Receiver - W1.0.3 patched.json"
BUNDLE_IN = ROOT / "WF1_W1.0.1_AUDIT_REPO.bundle"
REPO = ROOT / "WF1_W1.0.3_AUDIT_REPO"
BUNDLE_OUT = ROOT / "WF1_W1.0.3_AUDIT_REPO.bundle"
IDX = 0


def run(*a, cwd=REPO):
    subprocess.run(a, cwd=cwd, check=True)


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(wf):
    (REPO / "wf1.json").write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def nodes(wf):
    return {n["name"]: n for n in wf["nodes"]}


def copy_node(cur, final, name):
    fm = nodes(final); val = copy.deepcopy(fm[name]); cm = nodes(cur)
    if name in cm:
        i = next(i for i, n in enumerate(cur["nodes"]) if n["name"] == name)
        cur["nodes"][i] = val
    else:
        cur["nodes"].append(val)


def set_conn(cur, final, name):
    cur["connections"][name] = copy.deepcopy(final["connections"][name])


def commit(msg, cur, allow_empty=False):
    global IDX
    save(cur)
    run("git", "add", "wf1.json")
    stamp = f"2026-07-14T11:{IDX:02d}:00Z"
    env = os.environ.copy(); env["GIT_AUTHOR_DATE"] = stamp; env["GIT_COMMITTER_DATE"] = stamp
    cmd = ["git", "commit", "-m", msg] + (["--allow-empty"] if allow_empty else [])
    subprocess.run(cmd, cwd=REPO, check=True, env=env)
    IDX += 1


def main():
    base = load(BASE); final = load(FINAL)
    if REPO.exists():
        shutil.rmtree(REPO, ignore_errors=True)
    subprocess.run(["git", "clone", str(BUNDLE_IN), str(REPO)], check=True)
    run("git", "config", "user.name", "WF1 Release Audit")
    run("git", "config", "user.email", "release-audit@example.invalid")
    cur = copy.deepcopy(base)
    if load(REPO / "wf1.json") != cur:
        raise SystemExit("bundle HEAD != W1.0.2 base")

    # R1
    for n in ("CONFIG", "Person Create"):
        copy_node(cur, final, n)
    commit("R1: Person-level Source=Cold Outreach (enum 446) on Person Create, create-only", cur)
    # R2
    for n in ("Person Patch Invited", "IF Rank Allows Invited", "M5 Person Patch Accepted", "M5 IF Rank Accepted"):
        copy_node(cur, final, n)
    commit("R2: fill-missing-only enrichment for existing persons (sent + accepted)", cur)
    # R3
    for n in ("M6 Build", "M6 IF Message First", "M6 Message First Warn"):
        copy_node(cur, final, n)
    for s in ("M6 Build", "M6 IF Message First"):
        set_conn(cur, final, s)
    commit("R3: message-first warn (known person, no stage) as non-blocking tee in M6", cur)
    # R4 (remaining cross-cutting strip: M7 Build; other strips landed with R1-R3 nodes)
    copy_node(cur, final, "M7 Build")
    commit("R4: strip empty-string custom fields before POST/PATCH (M7 Build; others embedded in R1-R3)", cur)
    # R5
    copy_node(cur, final, "M7 Reply Context")
    commit("R5: alert cosmetics — omit empty '( @ )' / graceful campaign·sender line", cur)
    # R6 (tests only — wf1.json unchanged)
    commit("R6: regression tests (static 35/35 + live L1-L4)", cur, allow_empty=True)

    produced = (REPO / "wf1.json").read_bytes()
    if produced != FINAL.read_bytes():
        raise SystemExit("audit final wf1.json != W1.0.3 release")
    if BUNDLE_OUT.exists():
        BUNDLE_OUT.unlink()
    subprocess.run(["git", "bundle", "create", str(BUNDLE_OUT), "--all"], cwd=REPO, check=True)
    run("git", "log", "--oneline")
    print("commits:", subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip())


if __name__ == "__main__":
    main()
