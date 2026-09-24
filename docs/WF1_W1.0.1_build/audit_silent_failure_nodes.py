#!/usr/bin/env python3
"""AUDIT - the silent-failure factory: onError=continueRegularOutput + real code in an EXPRESSION.

The combination is what let WF-2's reply alert fail 25/25 times for eleven days while every
execution reported 'success':
  * the expression parser rejects the code           -> the node errors
  * onError=continueRegularOutput swallows the error -> the execution stays green
  * anything checking 'did the node run' says yes    -> monitoring confirms the lie

A node is FLAGGED when it both (a) swallows errors and (b) carries an expression containing real
JavaScript - arrow functions, const/let, try/catch, IIFEs. Expressions doing simple field reads
(`={{ $json.x }}`) are fine and are not flagged.

Severity: a node whose expression is LONG and nested is more likely to trip the parser, so length
and construct count are reported to rank the risk rather than leaving it binary.

READ-ONLY.
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS = {"WF-1": "2jdjKM2NJr473GdA", "WF-2": "jp7rum9Z0YDJkQWv",
             "WF-2R": "U8Bb7Pdq7S6nzYPa", "WF-2S": "6Y92ryBwYoy6z0Jx",
             "WF-2H": "nK3yIOqRcBearV8s", "WF-ERR": "BbrXPABgOaaTJjD6"}
CONSTRUCTS = [(r"\(\(\)\s*=>", "IIFE"), (r"=>", "arrow"), (r"\bconst\b", "const"),
              (r"\blet\b", "let"), (r"\btry\s*{", "try/catch"), (r"\bfunction\b", "function"),
              (r"\.replace\(", ".replace"), (r"\?\?", "??")]


def n8n(p):
    r = urllib.request.Request(BASE + p, headers={"X-N8N-API-KEY": KEY,
                                                  "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def expressions(params, path=""):
    """Yield (json-path, expression string) for every '={{ ... }}' value in the node params."""
    if isinstance(params, dict):
        for k, v in params.items():
            yield from expressions(v, f"{path}.{k}" if path else k)
    elif isinstance(params, list):
        for i, v in enumerate(params):
            yield from expressions(v, f"{path}[{i}]")
    elif isinstance(params, str) and params.startswith("={{"):
        yield path, params


flagged, safe_swallowers, total_nodes = [], 0, 0
for label, wid in WORKFLOWS.items():
    wf = n8n(f"/api/v1/workflows/{wid}")
    for n in wf["nodes"]:
        total_nodes += 1
        swallows = n.get("onError") == "continueRegularOutput"
        if not swallows:
            continue
        worst = None
        for path, expr in expressions(n.get("parameters") or {}):
            found = [name for rx, name in CONSTRUCTS if re.search(rx, expr)]
            if not found:
                continue
            cand = {"wf": label, "node": n["name"], "type": n["type"].split(".")[-1],
                    "param": path, "len": len(expr), "constructs": sorted(set(found))}
            if worst is None or cand["len"] > worst["len"]:
                worst = cand
        if worst:
            flagged.append(worst)
        else:
            safe_swallowers += 1

flagged.sort(key=lambda r: -r["len"])
print(f"nodes scanned: {total_nodes}")
print(f"nodes that swallow errors (onError=continueRegularOutput): "
      f"{len(flagged) + safe_swallowers}")
print(f"  ...of those, carrying CODE in an expression -> FLAGGED: {len(flagged)}")
print(f"  ...carrying only simple expressions -> fine: {safe_swallowers}\n")

if flagged:
    print(f"{'wf':<7} {'node':<26} {'type':<14} {'len':>6}  constructs")
    print("-" * 100)
    for r in flagged:
        print(f"{r['wf']:<7} {r['node']:<26} {r['type']:<14} {r['len']:>6}  "
              f"{', '.join(r['constructs'])}")
        print(f"        param: {r['param']}")
else:
    print("no node combines error-swallowing with code-in-an-expression")

print("\nRANKING NOTE: longer + more nested expressions are likelier to trip the parser. "
      "The two that actually failed (WF-2 Reply Alert 1154 chars, Nurture Alert 300) were the "
      "longest of their kind before today's fix.")
json.dump(flagged, open(os.path.join(HERE, "wf1-release-evidence",
                                     "audit_silent_failure_nodes.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("\nwrote wf1-release-evidence/audit_silent_failure_nodes.json")
