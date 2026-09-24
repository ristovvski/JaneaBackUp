#!/usr/bin/env python3
"""WF-2: reply channel -> team, and the auditor's `|| 0` degenerate-path finding. One window.

ITEM 4 - CONFIG.slack_channel_replies: C0B8GCVNR5W -> C07LTD8UT70. Ops/errors stay on ops. This is
the node-level routing already in place (`Reply Alert` and `Nurture Alert` read
slack_channel_replies; all eight Ops Warn nodes read slack_channel_ops), so a single CONFIG value
moves exactly the reply alerts and nothing else.

ITEM 3 - the auditor's medium finding, in two parts:

  (a) R Lead List's candidate expression has NO `__person_id` fallback, while the three branches
      added in 4c do. That inconsistency is the finding: on the reply branch, a person resolved
      without a candidate array would query nothing. Unify R to the same shape.

  (b) `|| 0` as the degenerate value. person_id=0 is a REAL-LOOKING id: it reads as a query for
      person zero rather than as "we have no person", and Pipedrive answering it plausibly is
      exactly the class in section 9b. Replaced with -1, which cannot be a Pipedrive person id, so
      a degenerate read is unambiguous in the URL and in the logs.

NOT DONE, and deliberately: the auditor asked for an explicit unresolved BRANCH. A real branch
needs an IF node in front of four HTTP nodes - graph surgery on the wave path, which is P0-1b's
gate class, not a config edit. Nor did I add a `__lead_read_unresolved` flag: section 9b.0b (set
today) forbids emitting a blindness flag with no consumer, and this one has none yet. The
degenerate case is already visible without a new flag - `__lead_candidates_read` and a
`person_id=-1` in the request - so nothing is hidden by waiting. Carrying the branch to Nik.
"""
import argparse, json, os, re, ssl, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"
BRANCHES = {"R Lead List": "R Person Pick", "Lead List": "Person Id Final",
            "B Lead List": "B Lead Ctx", "U Lead List": "U Lead Ctx"}


def cand_expr(src):
    j = f"$('{src}').first().json"
    return (f"(({j}.__person_candidates && {j}.__person_candidates.length)"
            f" ? {j}.__person_candidates : [{j}.__person_id])")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

# ---------- item 4: CONFIG channel
cfg = N["CONFIG"]
blob = json.dumps(cfg["parameters"], ensure_ascii=False)
m = re.search(r'slack_channel_replies\\":\s*\\"([A-Z0-9]+)\\"', blob)
cur_ch = m.group(1) if m else None
print(f"\nCONFIG.slack_channel_replies currently: {cur_ch}")
if cur_ch is None:
    sys.exit("could not locate slack_channel_replies - refusing to edit blind")
new_blob = blob.replace(f'slack_channel_replies\\": \\"{cur_ch}\\"',
                        f'slack_channel_replies\\": \\"{TEAM}\\"')
if cur_ch != TEAM and new_blob == blob:
    sys.exit("channel replacement did not apply - refusing to guess at the shape")
new_cfg_params = json.loads(new_blob)

# guard: ops nodes must NOT move. Verified by node wiring, not by hope.
reply_nodes = [n["name"] for n in wf["nodes"]
               if n["type"].endswith("slack")
               and "slack_channel_replies" in json.dumps(n.get("parameters") or {})]
ops_nodes = [n["name"] for n in wf["nodes"]
             if n["type"].endswith("slack")
             and "slack_channel_ops" in json.dumps(n.get("parameters") or {})]
print(f"  nodes that will move to {TEAM}: {reply_nodes}")
print(f"  nodes staying on ops ({len(ops_nodes)}): {ops_nodes}")
if any(n.startswith("Ops Warn") for n in reply_nodes):
    sys.exit("an Ops Warn node reads slack_channel_replies - routing spec would be violated")

# ---------- item 3: expressions
expr_changes = []
for lst, src in BRANCHES.items():
    pg = ((N[lst]["parameters"].get("options") or {}).get("pagination") or {}).get("pagination")
    if not pg:
        sys.exit(f"{lst}: no pagination - run the Finding 4 patches first")
    want_param = f"={{{{ {cand_expr(src)}[$pageCount] || -1 }}}}"
    want_complete = f"={{{{ $pageCount >= ({cand_expr(src)}.length - 1) }}}}"
    got_param = pg["parameters"]["parameters"][0]["value"]
    if got_param != want_param:
        expr_changes.append((lst, got_param, want_param, want_complete))

print("\n--- planned ---")
if cur_ch != TEAM:
    print(f"  - CONFIG.slack_channel_replies {cur_ch} -> {TEAM}")
else:
    print("  (channel already team)")
for lst, old, new, _ in expr_changes:
    print(f"  - {lst}: person_id expression")
    print(f"      old: {old}")
    print(f"      new: {new}")
if not expr_changes and cur_ch == TEAM:
    print("  (already applied)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_channel_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(wf, indent=2, ensure_ascii=False))

cfg["parameters"] = new_cfg_params
for lst, _, new_param, new_complete in expr_changes:
    pg = N[lst]["parameters"]["options"]["pagination"]["pagination"]
    pg["parameters"]["parameters"][0]["value"] = new_param
    pg["completeExpression"] = new_complete

was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
try:
    d = stripped_keys(wf)
    if d:
        print(f"stripping UI-only settings keys: {d}")
    n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
finally:
    if was:
        n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
ablob = json.dumps(an["CONFIG"]["parameters"], ensure_ascii=False)
problems = []
m2 = re.search(r'slack_channel_replies\\":\s*\\"([A-Z0-9]+)\\"', ablob)
if not m2 or m2.group(1) != TEAM:
    problems.append(f"slack_channel_replies={m2.group(1) if m2 else None}")
m3 = re.search(r'slack_channel_ops\\":\s*\\"([A-Z0-9]+)\\"', ablob)
if not m3 or m3.group(1) != OPS:
    problems.append(f"slack_channel_ops CHANGED to {m3.group(1) if m3 else None}")
for lst, src in BRANCHES.items():
    pg = ((an[lst]["parameters"].get("options") or {}).get("pagination") or {}).get("pagination") or {}
    v = pg.get("parameters", {}).get("parameters", [{}])[0].get("value", "")
    if "|| -1" not in v:
        problems.append(f"{lst}: degenerate value not -1")
    if "__person_id" not in v:
        problems.append(f"{lst}: no __person_id fallback")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')} (was {was})")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
sys.exit(1 if problems else 0)
