#!/usr/bin/env python3
"""Suppress Slack link previews on EVERY alert post - WF-1 and WF-2, team and ops.

Nik: no reason for previews anywhere. A LinkedIn URL in the Details block stays clickable; Slack
just stops expanding it into a profile card that dwarfs the alert.

All 18 Slack nodes are typeVersion 2.3 and already carry `otherOptions: {}`, so the flags go in
there as flat booleans - the names are Slack's own API parameters, which is what the n8n node
forwards.

HONEST LIMIT, same as the batching fix: read-back proves the value is STORED, not that the node
forwards it. The failure mode is benign - previews simply continue - so the verification is
observational: the next alert either shows a preview card or it does not. Not claiming otherwise.
"""
import argparse, copy, json, os, ssl, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = {"2jdjKM2NJr473GdA": "WF-1", "jp7rum9Z0YDJkQWv": "WF-2"}
FLAGS = {"unfurl_links": False, "unfurl_media": False}


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

plans = {}
for wid, tag in TARGETS.items():
    wf = n8n(f"/api/v1/workflows/{wid}")
    orig = copy.deepcopy(wf)
    slack = [n for n in wf["nodes"] if n["type"].endswith("slack")]
    todo = []
    for n in slack:
        oo = (n.setdefault("parameters", {}).setdefault("otherOptions", {}))
        if not isinstance(oo, dict):
            raise SystemExit(f"{tag}/{n['name']}: otherOptions is {type(oo).__name__}, "
                             f"refusing to overwrite it blind")
        if all(oo.get(k) is v for k, v in FLAGS.items()):
            continue
        oo.update(FLAGS)
        todo.append(n["name"])
    plans[wid] = (wf, orig, slack, todo)
    print(f"{tag}: {len(slack)} Slack nodes, {len(todo)} to update")
    for nm in todo:
        print(f"   {nm}")

if not any(p[3] for p in plans.values()):
    print("\n(already applied everywhere)")
    sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
problems = []
for wid, (wf, orig, slack, todo) in plans.items():
    tag = TARGETS[wid]
    if not todo:
        continue
    with open(os.path.join(HERE, f"{tag.lower()}_backup_before_unfurl_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(orig, indent=2, ensure_ascii=False))
    d = stripped_keys(wf)
    if d:
        print(f"  {tag}: stripping {d}")
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(wf))

    after = n8n(f"/api/v1/workflows/{wid}")
    aslack = [n for n in after["nodes"] if n["type"].endswith("slack")]
    for n in aslack:
        oo = (n.get("parameters") or {}).get("otherOptions") or {}
        if oo.get("unfurl_links") is not False or oo.get("unfurl_media") is not False:
            problems.append(f"{tag}/{n['name']}: {json.dumps(oo)}")
    if after.get("active") is not orig.get("active"):
        problems.append(f"{tag} active={after.get('active')}")
    if len(after["nodes"]) != len(orig["nodes"]):
        problems.append(f"{tag} node count changed")
    print(f"  {tag} versionId={after.get('versionId')} active={after.get('active')} "
          f"slack_nodes={len(aslack)} all_suppressed="
          f"{all(((n.get('parameters') or {}).get('otherOptions') or {}).get('unfurl_links') is False for n in aslack)}")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print("\nNOTE: this proves the flags are STORED. Whether Slack suppresses the card is observational")
print("- the next alert shows it or it does not. Benign either way.")
sys.exit(1 if problems else 0)
