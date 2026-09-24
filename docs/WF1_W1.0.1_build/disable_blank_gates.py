#!/usr/bin/env python3
"""DISABLE both blank-body gates. Safety first, diagnosis second.

Person-8768306e DID reply at 03:34 - an attachment with no text. The gate I shipped treats
"no text" as "not a reply", so it is currently suppressing attachment-only replies: alert, label,
DNC row, activity, task, all silenced for a real responder. A false alert beats a missed real reply,
so the gates come out now and go back only when the attachment marker is known from the wire.

My statics DID cover attachments - with `message_type: 'ATTACHMENT'`, a field I took from
`M7 Build.render()` rather than from a real payload. Heath's `recent_messages` entries carry exactly
['creation_time', 'is_reply', 'message']. I tested a shape HeyReach does not send, and green
statics certified it.

WF-1: Switch[3] -> M7 IF Email Present, directly, as before the gate.
WF-2: Switch Event[1] -> IF Nurture REPLIED + IF Unknown Marker, directly, as before the gate.
The gate nodes are LEFT IN PLACE but disconnected and marked disabled - preserved for the fix, not
deleted (an incident artefact is never deleted before it is understood).

The WF-1 alert excerpt (`Reply: ...`) STAYS. It is what would have shown '[attachment]' or
'[empty message]' in the channel and made this visible on day one.
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
WF1 = "2jdjKM2NJr473GdA"
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


def restore(wfid, switch_name, out_index, gate_name, skip_name, targets, label):
    wf = n8n("/api/v1/workflows/%s" % wfid)
    orig = copy.deepcopy(wf)
    C = wf.setdefault("connections", {})
    N = {n["name"]: n for n in wf["nodes"]}
    sw = (C.get(switch_name) or {}).get("main") or []
    if len(sw) <= out_index:
        sys.exit("%s: %s has %d outputs" % (label, switch_name, len(sw)))
    before = [l["node"] for l in (sw[out_index] or []) if l]
    print("\n=== %s ===" % label)
    print("  %s[%d] before: %s" % (switch_name, out_index, before))
    if gate_name not in before:
        print("  gate already disconnected - nothing to do")
        return wf, orig, False
    sw[out_index] = [{"node": t, "type": "main", "index": 0} for t in targets]
    C[switch_name]["main"] = sw
    C.pop(gate_name, None)
    for nm in (gate_name, skip_name):
        if nm in N:
            N[nm]["disabled"] = True
    print("  %s[%d] after : %s" % (switch_name, out_index, targets))
    print("  gate + skip nodes marked disabled, connections removed (kept, not deleted)")
    return wf, orig, True


w1, o1, c1 = restore(WF1, "Switch", 3, "M7 Blank Reply Gate", "M7 Blank Reply Skipped",
                     ["M7 IF Email Present"], "WF-1 HeyReach")
w2, o2, c2 = restore(WF2, "Switch Event", 1, "Blank Body Gate", "Blank Body Skipped",
                     ["IF Nurture REPLIED", "IF Unknown Marker"], "WF-2 Smartlead")

if not a.deploy:
    print("\n--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wf, orig, changed, wfid, label in ((w1, o1, c1, WF1, "wf1"), (w2, o2, c2, WF2, "wf2")):
    if not changed:
        continue
    p = os.path.join(HERE, "%s_backup_before_gate_disable_%d.json" % (label, stamp))
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(orig, indent=2, ensure_ascii=False))
    print("\nbackup: %s" % os.path.basename(p))
    sk = stripped_keys(wf)
    if sk:
        print("stripped UI-only settings keys: %s" % sk)
    n8n("/api/v1/workflows/%s" % wfid, "PUT", put_body(wf))
    after = n8n("/api/v1/workflows/%s" % wfid)
    AC = after.get("connections") or {}
    AN = {n["name"]: n for n in after["nodes"]}
    problems = []
    if label == "wf1":
        s = [l["node"] for l in (((AC.get("Switch") or {}).get("main") or [[]] * 4)[3] or [])]
        if s != ["M7 IF Email Present"]:
            problems.append("Switch[3] -> %s" % s)
        if AC.get("M7 Blank Reply Gate"):
            problems.append("gate still has outgoing connections")
        if not AN.get("M7 Blank Reply Gate", {}).get("disabled"):
            problems.append("gate not marked disabled")
        if "Reply: " not in (AN["M7 Build"]["parameters"]["jsCode"]):
            problems.append("alert excerpt was lost - it must STAY")
    else:
        s = [l["node"] for l in (((AC.get("Switch Event") or {}).get("main") or [[]] * 2)[1] or [])]
        if sorted(s) != sorted(["IF Nurture REPLIED", "IF Unknown Marker"]):
            problems.append("Switch Event[1] -> %s" % s)
        if AC.get("Blank Body Gate"):
            problems.append("gate still has outgoing connections")
    if not after.get("active"):
        problems.append("WORKFLOW IS INACTIVE after the PUT")
    print("  %s: %s  versionId=%s active=%s nodes=%d"
          % (label.upper(), "CLEAN" if not problems else "PROBLEMS",
             after.get("versionId"), after.get("active"), len(after["nodes"])))
    for pr in problems:
        print("    -", pr)
    if problems:
        sys.exit(1)
print("\nboth gates disabled. Attachment-only replies flow again.")
