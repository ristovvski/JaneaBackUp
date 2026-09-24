#!/usr/bin/env python3
"""Record Nik's routing ruling in the deployed gate's own comment. Comment-only change.

The parked question was: where should manual-conversation replies surface instead?
RULING (Nik, 2026-08-28): NOWHERE. Silent CRM activity write and nothing else.

Writing it into the node matters more than the doc: the next person to read this gate will wonder
whether the silence is deliberate or an oversight, and the answer has to be where they are looking.
"""
import argparse, copy, json, os, ssl, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"

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
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF1}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["M7 Alert Gate"]["parameters"]["jsCode"]
if "RULING (Nik, 2026-08-28)" in js:
    sys.exit("ruling already recorded")

OLD = """// CAMPAIGN-ORIGIN GATE (Melisa, 2026-08-27): "We shouldn't get notifications about personal chats"""
if OLD not in js:
    sys.exit("gate comment not found verbatim - refusing to patch blind")
NEW = """// CAMPAIGN-ORIGIN GATE (Melisa, 2026-08-27): "We shouldn't get notifications about personal chats"""
js2 = js.replace(
    "// replies from being lost, and must not resurrect a personal chat that has no identity either.",
    """// replies from being lost, and must not resurrect a personal chat that has no identity either.
//
// RULING (Nik, 2026-08-28) — WHERE DO MANUAL-THREAD REPLIES GO INSTEAD? **NOWHERE.**
// A manual conversation gets the silent CRM activity write and nothing else: no #lead-processing
// alert, no thread note, no digest line, no alternate channel, no telemetry line. The exec's own
// conversations are the exec's own business; the CRM records them so the history exists, and the
// system never announces them to anyone. This silence is DELIBERATE - do not "restore" it as a
// quiet line somewhere on the assumption it was an oversight.""", 1)
if js2 == js:
    sys.exit("placement anchor not found - refusing to guess")
N["M7 Alert Gate"]["parameters"]["jsCode"] = js2
print("comment prepared; diff is comment-only:")
print(f"  code lines before: {len(js.splitlines())}  after: {len(js2.splitlines())}")
stripped_a = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
stripped_b = "\n".join(l for l in js2.splitlines() if not l.strip().startswith("//"))
print(f"  executable body identical: {stripped_a == stripped_b}")
if stripped_a != stripped_b:
    sys.exit("executable body changed - this was meant to be comment-only")

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)
stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_ruling_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
live = AN["M7 Alert Gate"]["parameters"]["jsCode"]
problems = []
if "RULING (Nik, 2026-08-28)" not in live:
    problems.append("ruling not live")
if "__manual_thread" not in live:
    problems.append("gate logic missing")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
live_body = "\n".join(l for l in live.splitlines() if not l.strip().startswith("//"))
if live_body != stripped_a:
    problems.append("executable body differs from before")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
