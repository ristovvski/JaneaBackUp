#!/usr/bin/env python3
"""Move `IF Unknown Marker` behind the blank-body gate on WF-2's REPLIED branch.

I had left it ungated on the argument that an unknown-campaign-marker warning is about the
campaign, not about the reply. The linter flagged it, correctly: by the rule as written - no alert
reachable from a reply event without a non-blank body check - it is an alert on a reply branch.
Writing myself an exemption to make my own rule pass is the wrong way round, so the wiring moves.

Coverage cost, measured rather than asserted: `Switch Event[0]` (SENT) also feeds
`IF Unknown Marker`, so a mis-marked campaign still warns on every send. What is lost is the warning
on a blank-body reply from a mis-marked campaign - an event that, by the gate's whole premise, is
not a reply at all.
"""
import argparse
import copy
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, att=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and att < 5:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:300]))
    except Exception:
        if att < 3:
            time.sleep(6)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n("/api/v1/workflows/%s" % WF2)
ORIG = copy.deepcopy(wf)
C = wf.setdefault("connections", {})
N = {n["name"]: n for n in wf["nodes"]}
if "Blank Body Gate" not in N:
    sys.exit("blank-body gate is not deployed - run p_wf2_blank_body_gate.py first")

sw = (C.get("Switch Event") or {}).get("main") or []
before = [l["node"] for l in (sw[1] or []) if l]
print("Switch Event[1] before: %s" % before)
if "IF Unknown Marker" not in before:
    print("already gated - nothing to do")
    sys.exit(0)
sw[1] = [l for l in (sw[1] or []) if l.get("node") != "IF Unknown Marker"]
C["Switch Event"]["main"] = sw

g = (C.get("Blank Body Gate") or {}).get("main") or [[], []]
true_out = [l["node"] for l in (g[0] or []) if l]
if "IF Unknown Marker" not in true_out:
    g[0] = list(g[0] or []) + [{"node": "IF Unknown Marker", "type": "main", "index": 0}]
C["Blank Body Gate"]["main"] = g

print("Switch Event[1] after : %s" % [l["node"] for l in (sw[1] or []) if l])
print("gate TRUE output after: %s" % [l["node"] for l in (g[0] or []) if l])

# SENT still covers the marker check - assert it rather than claim it
sent = [l["node"] for l in (sw[0] or []) if l]
print("Switch Event[0] (SENT) still feeds: %s" % sent)
if "IF Unknown Marker" not in sent:
    print("  WARNING: SENT no longer covers the marker check - coverage claim does not hold")

if not a.deploy:
    print("\n--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "wf2_backup_before_marker_gate_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: wf2_backup_before_marker_gate_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % WF2, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % WF2)
AC = after.get("connections") or {}
s1 = [l["node"] for l in (((AC.get("Switch Event") or {}).get("main") or [[]] * 2)[1] or [])]
gt = [l["node"] for l in (((AC.get("Blank Body Gate") or {}).get("main") or [[]])[0] or [])]
problems = []
if "IF Unknown Marker" in s1:
    problems.append("still wired direct from Switch Event[1]")
if "IF Unknown Marker" not in gt:
    problems.append("not on the gate's TRUE output")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
if not after.get("active"):
    problems.append("WF-2 IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  WF-2 versionId=%s active=%s nodes=%d" % (after.get("versionId"), after.get("active"),
                                                  len(after["nodes"])))
print("  Switch Event[1] -> %s" % s1)
print("  Blank Body Gate TRUE -> %s" % gt)
sys.exit(1 if problems else 0)
