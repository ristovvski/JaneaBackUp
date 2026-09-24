#!/usr/bin/env python3
"""READ ONLY, estate-wide: attribution and justification fields frozen as constants in write paths.

VERSION 2. Version 1 reported "5 findings, all benign" and MISSED BOTH KNOWN CASES - WF-1's
`owner_id: CFG.melisa_user_id` and the removal path's `removed_reason: 'rule_change_...'`. The bug
was the scope: it only looked inside MUTATING nodes, and in this estate the request body is almost
always assembled in a preceding **Code** node, then handed to the HTTP or dataTable node. So it
searched everywhere except where the constants live. A confident zero from the wrong scope is the
exact failure this sweep exists to find.

VERSION 2 scope: every node from which a mutating node is REACHABLE. Three categories, reported
separately because they are not equally wrong:

  LITERAL   a quoted constant or bare id            - the Heath / removal-path shape
  CONFIG    a single CONFIG constant standing in    - the melisa_user_id shape: looks configurable,
            for a per-event value                     is still one frozen value for every record
  (benign)  a node whose whole purpose is that      - e.g. `status: 'expired'` in an expiry job.
            value                                     Reported, flagged, never silently dropped.
"""
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))

WATCH = ("owner_id", "user_id", "assigned_to", "creator_user_id",
         "removed_reason", "reason", "entry_type", "reply_category", "date_precision",
         "source_ref", "status", "medium")
MUT_OPS = ("insert", "update", "upsert", "deleteRows", "delete")


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=240, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        raise


def mutating(n):
    t, p = n["type"], (n.get("parameters") or {})
    if t.endswith("httpRequest"):
        return str(p.get("method", "GET")).upper() in ("POST", "PUT", "PATCH", "DELETE")
    if t.endswith("dataTable"):
        return str(p.get("operation")) in MUT_OPS
    return t.endswith("pipedrive") or "executeWorkflow" in t


def feeders(wf):
    """Nodes from which at least one mutating node is reachable - the real write path."""
    C = wf.get("connections") or {}
    nodes = {n["name"]: n for n in wf["nodes"]}
    muts = {nm for nm, n in nodes.items() if mutating(n)}
    rev = {}
    for src, spec in C.items():
        for b in (spec.get("main") or []):
            for l in (b or []):
                if l:
                    rev.setdefault(l["node"], set()).add(src)
    seen, stack = set(muts), list(muts)
    while stack:
        cur = stack.pop()
        for p in rev.get(cur, ()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen, muts


cur, wfs = None, []
while True:
    q = {"limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
    wfs += d.get("data") or []
    cur = d.get("nextCursor")
    if not cur:
        break
print("workflows: %d" % len(wfs))

findings = []
for w in wfs:
    full = n8n("/api/v1/workflows/%s" % w["id"])
    path, muts = feeders(full)
    for n in full["nodes"]:
        if n["name"] not in path:
            continue
        p = n.get("parameters") or {}
        blob = json.dumps(p, ensure_ascii=False)
        js = p.get("jsCode") or ""
        for k in WATCH:
            for m in re.finditer(r"\b%s\s*:\s*('[^']{1,90}'|\"[^\"]{1,90}\")" % k, js):
                findings.append({"wf": w["name"], "active": bool(full.get("active")),
                                 "node": n["name"], "kind": "LITERAL", "key": k,
                                 "value": m.group(1)[:90], "is_mut": n["name"] in muts})
            for m in re.finditer(r"\b%s\s*:\s*(?:CFG|cfg|C)\.([A-Za-z0-9_]+)" % k, js):
                findings.append({"wf": w["name"], "active": bool(full.get("active")),
                                 "node": n["name"], "kind": "CONFIG", "key": k,
                                 "value": "CONFIG." + m.group(1), "is_mut": n["name"] in muts})
            for m in re.finditer(r"\b%s\s*:\s*\$\(['\"]CONFIG['\"]\)\.item\.json\.([A-Za-z0-9_]+)"
                                 % k, js):
                findings.append({"wf": w["name"], "active": bool(full.get("active")),
                                 "node": n["name"], "kind": "CONFIG", "key": k,
                                 "value": "CONFIG." + m.group(1), "is_mut": n["name"] in muts})
        cols = ((p.get("columns") or {}).get("value") or {})
        for k, v in cols.items():
            s = str(v)
            if k in WATCH and not (s.startswith("=") or "{{" in s):
                findings.append({"wf": w["name"], "active": bool(full.get("active")),
                                 "node": n["name"], "kind": "LITERAL", "key": k,
                                 "value": s[:90], "is_mut": True})

# de-duplicate
uniq, seen = [], set()
for f in findings:
    sig = (f["wf"], f["node"], f["key"], f["value"])
    if sig in seen:
        continue
    seen.add(sig)
    uniq.append(f)

print("\n=== SELF-CHECK: does v2 find the two we already know about? ===")
known = [("WF-1 HeyReach Receiver", "owner_id", "CONFIG.melisa_user_id"),
         ("dnc_s4_retirement_removal", "removed_reason", None)]
for wfname, key, val in known:
    hits = [f for f in uniq if wfname.split()[0] in f["wf"] and f["key"] == key]
    print("  %-34s %-16s -> %s" % (wfname[:34], key,
                                   ("FOUND: " + ", ".join(sorted({h["value"] for h in hits})))
                                   if hits else "not found (expected if already fixed)"))

act = [f for f in uniq if f["active"]]
print("\n=== findings on ACTIVE workflows (%d of %d total) ===" % (len(act), len(uniq)))
by = {}
for f in act:
    by.setdefault(f["wf"], []).append(f)
for nm, rows in sorted(by.items()):
    print("\n  %s" % nm)
    for f in sorted(rows, key=lambda x: (x["kind"], x["node"])):
        print("     %-7s %-28s %-16s = %s" % (f["kind"], f["node"][:28], f["key"], f["value"]))

print("\n=== findings on inactive workflows (%d) ===" % (len(uniq) - len(act)))
for f in sorted([f for f in uniq if not f["active"]], key=lambda x: (x["wf"], x["node"])):
    print("     %-34s %-26s %-16s = %s" % (f["wf"][:34], f["node"][:26], f["key"], f["value"]))

with open(os.path.join(HERE, "hardcoded_constants_sweep.json"), "w", encoding="utf-8") as f:
    json.dump(uniq, f, ensure_ascii=False, indent=1)
print("\n-> hardcoded_constants_sweep.json   (%d findings)" % len(uniq))
sys.exit(0)
