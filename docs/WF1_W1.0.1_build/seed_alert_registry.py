#!/usr/bin/env python3
"""Registry seed, STEP 2 — bracketed read-modify-write of __alerted_v1 on WF-1 and WF-2 staticData.

This store has cost us 113 claims to lost-update races, so the shape is deliberate:
  1. SNAPSHOT staticData to disk before touching anything (the bracket's opening)
  2. read-modify-write ONCE, additions only - never remove a key we did not add
  3. read back and assert: identical to the snapshot EXCEPT the additions, nothing lost

Additions are keyed per workflow: a WF-1 key is written to WF-1's store only. Seeding a key into the
wrong workflow's registry would silence an alert that workflow has never sent.

Idempotent: a key already present keeps its ORIGINAL timestamp. Re-running adds nothing.
"""
import argparse, copy, json, os, ssl, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
# The two workflows use DIFFERENT registry key names - WF-1 M7 writes __alerted_v1, WF-2's
# First Reply Gate writes __alert_delivered. Seeding one name into the other workflow creates a
# registry nothing reads: the write verifies clean and suppresses nothing. Second instance of that
# trap in this one script (the first was staticData.global nesting).
WFS = {"WF-1": ("2jdjKM2NJr473GdA", "__alerted_v1"),
       "WF-2": ("jp7rum9Z0YDJkQWv", "__alert_delivered")}

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
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
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:250]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


seed = json.load(open(os.path.join(HERE, "alert_seed_list.json"), encoding="utf-8"))
per = {"WF-1": {}, "WF-2": {}}
for k, v in seed.items():
    per[v["wf"]][k] = v
print(f"seed list: {len(seed)} keys  (WF-1 {len(per['WF-1'])}, WF-2 {len(per['WF-2'])})")
ALAN = "Lf6bfaf70-90af-11f1-8dcf-2514ab8cea07|512995"

stamp = int(datetime.now(timezone.utc).timestamp())
for label, (wid, REGKEY) in WFS.items():
    wf = n8n(f"/api/v1/workflows/{wid}")
    sd = copy.deepcopy(wf.get("staticData") or {})
    if isinstance(sd, str):
        sd = json.loads(sd)
    # $getWorkflowStaticData('global') nests everything under staticData.global. Writing
    # __alerted_v1 at the TOP level would create a registry the workflow never reads: the seed
    # would verify clean and change nothing. Caught on the dry run - BEFORE said 0 keys while a
    # sibling key 'global' sat right there.
    G = sd.setdefault("global", {})
    reg = dict((G.get(REGKEY) or {}))
    print(f"\n=== {label} ===")
    print(f"  {REGKEY} BEFORE: {len(reg)} keys")
    snap = os.path.join(HERE, f"staticdata_snapshot_{label}_{stamp}.json")
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(sd, f, indent=1, ensure_ascii=False)
    print(f"  snapshot: {os.path.basename(snap)}  (global keys: "
          f"{sorted([k for k in G if k != REGKEY])})")

    add = {k: v["at"] for k, v in per[label].items() if k not in reg}
    print(f"  would add: {len(add)}  (already present: {len(per[label]) - len(add)})")
    if label == "WF-1":
        print(f"  Person-2f078c2e key in seed: {ALAN in per['WF-1']}  already in registry: {ALAN in reg}")
    if not a.live:
        continue
    if not add:
        print("  nothing to add - skipping the write entirely")
        continue

    newreg = dict(reg)
    newreg.update(add)
    sd["global"][REGKEY] = newreg
    wf["staticData"] = sd
    stripped_keys(wf)
    body = put_body(wf)
    body["staticData"] = sd
    n8n(f"/api/v1/workflows/{wid}", "PUT", body)

    after = n8n(f"/api/v1/workflows/{wid}")
    sd2 = after.get("staticData") or {}
    if isinstance(sd2, str):
        sd2 = json.loads(sd2)
    G2 = sd2.get("global") or {}
    reg2 = dict((G2.get(REGKEY) or {}))
    problems = []
    lost = [k for k in reg if k not in reg2]
    if lost:
        problems.append(f"LOST {len(lost)} pre-existing keys: {lost[:5]}")
    missing = [k for k in add if k not in reg2]
    if missing:
        problems.append(f"{len(missing)} additions did not land")
    changed = [k for k in reg if k in reg2 and reg2[k] != reg[k]]
    if changed:
        problems.append(f"{len(changed)} pre-existing timestamps were altered")
    for k in sd:
        if k != REGKEY and json.dumps(sd.get(k), sort_keys=True) != \
                json.dumps(sd2.get(k), sort_keys=True):
            problems.append(f"unrelated staticData key '{k}' changed")
    print(f"  AFTER: {len(reg2)} keys  (expected {len(reg) + len(add)})")
    if len(reg2) != len(reg) + len(add):
        problems.append(f"count mismatch: {len(reg2)} != {len(reg)}+{len(add)}")
    print(f"  verification: {'CLEAN - identical except additions' if not problems else 'PROBLEMS'}")
    for p in problems:
        print("    -", p)
    if label == "WF-1":
        print(f"  Person-2f078c2e key now present: {ALAN in reg2}")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
