#!/usr/bin/env python3
"""READ ONLY, and it must pass BEFORE the dev run.

The question that decides whether a "dev" run is safe: is every MUTATING node - the Pipedrive
PATCHes, the Smartlead unsubscribe, and critically the `Mark Done` dataTable writes - reachable
ONLY through the true branch of a FIRE_ gate?

Why this and not trust: a `Mark Done` reachable on the dev path would stamp registry rows as
projected without projecting them. That is unrecoverable by replay - the sweep would skip those
people forever, and the pre-post number would look like progress. The class is exactly the one this
estate keeps paying for: a write that reports success while achieving nothing.
"""
import json
import os
import ssl
import sys
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SWEEP = "8qVXtI2ez5o6a9hc"


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


wf = n8n("/api/v1/workflows/%s" % SWEEP)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}

MUTATION_OPS = ("upsert", "insert", "update", "deleteRows", "delete")


def is_mutating(n):
    t = n["type"]
    p = n.get("parameters") or {}
    if t.endswith("httpRequest"):
        return str(p.get("method", "GET")).upper() in ("POST", "PUT", "PATCH", "DELETE")
    if t.endswith("dataTable"):
        return str(p.get("operation")) in MUTATION_OPS
    if t.endswith("slack"):
        return True   # a post is an external side effect too
    return False


mutators = [n["name"] for n in wf["nodes"] if is_mutating(n)]
print("mutating nodes (%d):" % len(mutators))
for m in mutators:
    n = N[m]
    p = n.get("parameters") or {}
    print("  %-30s %-14s %s" % (m[:30], n["type"].split(".")[-1],
                                str(p.get("method") or p.get("operation") or "post")))


def reach(starts):
    seen, stack = set(), list(starts)
    while stack:
        cur = stack.pop()
        for b in ((C.get(cur) or {}).get("main") or []):
            for l in (b or []):
                if l and l["node"] not in seen:
                    seen.add(l["node"])
                    stack.append(l["node"])
    return seen


def reach_branch(node, index):
    """Reachable set from ONE output branch of one node."""
    outs = ((C.get(node) or {}).get("main") or [])
    if index >= len(outs):
        return set()
    first = [l["node"] for l in (outs[index] or []) if l]
    return set(first) | reach(first)


gates = [g for g in ("FIRE_PIPEDRIVE?", "FIRE_SMARTLEAD?") if g in N]
print("\nFIRE gates present: %s" % gates)

# everything reachable WITHOUT ever taking a FIRE gate's true branch = the dev path
trigger = next(n["name"] for n in wf["nodes"] if n["type"].endswith("webhook"))
blocked = set()
for g in gates:
    blocked |= reach_branch(g, 0)          # output 0 of an IF is TRUE

dev_path = set()
stack = [trigger]
seen = {trigger}
while stack:
    cur = stack.pop()
    outs = ((C.get(cur) or {}).get("main") or [])
    for bi, b in enumerate(outs):
        if cur in gates and bi == 0:
            continue                        # dev never takes the true branch
        for l in (b or []):
            if l and l["node"] not in seen:
                seen.add(l["node"])
                stack.append(l["node"])
dev_path = seen

print("\nnodes reachable on the DEV path: %d of %d" % (len(dev_path), len(wf["nodes"])))
leaks = sorted(m for m in mutators if m in dev_path)
darks = sorted(m for m in mutators if m not in dev_path)

print("\n--- mutating nodes DARK on the dev path (%d) ---" % len(darks))
for d in darks:
    print("  ok    %s" % d)
print("\n--- mutating nodes REACHABLE on the dev path (%d) ---" % len(leaks))
for l in leaks:
    n = N[l]
    print("  %s  %s (%s)" % ("SLACK " if n["type"].endswith("slack") else "LEAK  ", l,
                             n["type"].split(".")[-1]))

real = [l for l in leaks if not N[l]["type"].endswith("slack")]
print("\nverdict: %s" % ("CLEAR - a dev run writes nothing outside Slack"
                         if not real else "STOP - dev run would MUTATE: %s" % real))
if real:
    sys.exit(1)

# the Slack posts a dev run WILL make, so nobody is surprised by them
print("\nSlack side effects of a dev run:")
for l in leaks:
    if N[l]["type"].endswith("slack"):
        ch = json.dumps((N[l].get("parameters") or {}).get("channelId"), ensure_ascii=False)
        print("  %-22s -> %s" % (l, ch[:120]))
print("\nwebhook to fire: POST %s/webhook/%s" % (
    BASE.replace("/api/v1", ""),
    (N[trigger].get("parameters") or {}).get("path")))
sys.exit(0)
