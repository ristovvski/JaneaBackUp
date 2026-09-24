#!/usr/bin/env python3
"""Static sanity check on the freshly built dnc_i04_daily_diff.json before any live fire:
1. every connection target name is a real node name
2. every $('Node Name') reference inside jsCode resolves to a real node name
3. no node name collisions
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
wf = json.load(open(os.path.join(HERE, "dnc_i04_daily_diff.json"), encoding="utf-8"))
names = [n["name"] for n in wf["nodes"]]
name_set = set(names)

print(f"{len(names)} nodes, {len(name_set)} unique")
dupes = [n for n in name_set if names.count(n) > 1]
if dupes:
    print("DUPLICATE NAMES:", dupes)

bad_targets = []
for src, conn in wf["connections"].items():
    if src not in name_set:
        bad_targets.append(("SOURCE NOT A NODE", src))
    for branch in conn.get("main", []):
        for edge in branch:
            if edge["node"] not in name_set:
                bad_targets.append((src, edge["node"]))
if bad_targets:
    print("BAD CONNECTION TARGETS:")
    for a, b in bad_targets:
        print(" ", a, "->", b)
else:
    print("all connection targets resolve to real nodes")

ref_re = re.compile(r"\$\(\s*'([^']+)'\s*\)")
bad_refs = []
for n in wf["nodes"]:
    js = n.get("parameters", {}).get("jsCode", "")
    for m in ref_re.finditer(js):
        if m.group(1) not in name_set:
            bad_refs.append((n["name"], m.group(1)))
if bad_refs:
    print("BAD $('Node') REFERENCES IN CODE:")
    for a, b in bad_refs:
        print(" ", a, "references missing node:", b)
else:
    print("all $('Node') references in code resolve to real nodes")

# nodes with no incoming connection AND not a trigger -- likely orphaned
targets_hit = set()
for src, conn in wf["connections"].items():
    for branch in conn.get("main", []):
        for edge in branch:
            targets_hit.add(edge["node"])
triggers = {n["name"] for n in wf["nodes"] if "Trigger" in n["type"] or n["type"] == "n8n-nodes-base.webhook"}
orphans = [n for n in names if n not in targets_hit and n not in triggers]
if orphans:
    print("NODES WITH NO INCOMING CONNECTION (not a trigger):", orphans)
else:
    print("no orphaned non-trigger nodes")

# nodes with a jsCode error onError=stopWorkflow that sit deep in the graph without alerting
print("\nnode -> onError setting (non-default only):")
for n in wf["nodes"]:
    oe = n.get("onError")
    if oe:
        print(" ", n["name"], "->", oe)
