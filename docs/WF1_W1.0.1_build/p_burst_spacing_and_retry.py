#!/usr/bin/env python3
"""INCIDENT FIX: space WF-2S's replay burst, and armor WF-2's Pipedrive calls against 429.

ROOT CAUSE (unified with the auditor's staticData race): WF-2S's `Replay Into WF-2` posts to WF-2's
webhook once per item with NO batching, so up to 20 requests go out back-to-back and 20 WF-2
executions run concurrently. That single fact produces all three symptoms:
  * Pipedrive 429s - 20 parallel Person Search calls in one second (32 crashed SENTs today)
  * staticData last-writer-wins - overlapping executions read-modify-write the same registries
  * the recorded OOM-burst risk

FIX 1 - spacing. `Replay Into WF-2` gets batchSize 1 with a 10s interval; one WF-2 execution takes
~8s, so consecutive replays no longer overlap. Parameters-only.

  HONESTY ABOUT VERIFICATION: no node in this instance uses batching, so unlike the pagination fix
  I cannot copy a shape proven here. Today's lesson (options.pagination.pagination) is that a
  wrongly-nested option is ACCEPTED and then IGNORED. Read-back therefore proves nothing; only the
  next cycle's execution spacing does. That check is printed, not assumed.

FIX 2 - retry. `Person Search` had maxTries 3 at 1s and onError=None: three tries one second apart
during a rate-limit storm, then the execution dies. Raised to 5 tries at 5s (n8n's max wait), and
the unarmed Pipedrive writers get retry too. Note this does NOT make failures invisible - the nodes
still throw when retries are exhausted, which is what keeps crashed events unclaimed and replayable
under P0-1b. Armoring and honesty are not in tension here.
"""
import argparse, copy, json, os, ssl, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"
SPACING_MS = int(os.environ.get("SPACING_MS", "10000"))
# n8n caps waitBetweenTries at 5000ms; asking for more is silently clamped.
RETRY = {"retryOnFail": True, "maxTries": 5, "waitBetweenTries": 5000}
PD_NODES = ["Person Search", "Person Verify", "Org Search", "Org Create", "Person Patch",
            "Person Create", "Lead List", "Lead Create", "R Person Search", "R Person Verify",
            "R Lead List", "B Person Search", "U Person Search", "B Lead List", "U Lead List",
            "Lead Labels Union", "Reply Activity", "M7 Person Get"]


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

# ---------------------------------------------------------------- WF-2S spacing
ws = n8n(f"/api/v1/workflows/{WF2S}")
WS_ORIG = copy.deepcopy(ws)
wsn = {n["name"]: n for n in ws["nodes"]}
replay = wsn["Replay Into WF-2"]
cur = ((replay["parameters"].get("options") or {}).get("batching") or {})
print(f"WF-2S {ws.get('versionId')}  Replay Into WF-2 batching now: {json.dumps(cur)}")
replay["parameters"].setdefault("options", {})["batching"] = {
    "batch": {"batchSize": 1, "batchInterval": SPACING_MS}}
ws_change = json.dumps(cur) != json.dumps(replay["parameters"]["options"]["batching"])

# ---------------------------------------------------------------- WF-2 retry
w2 = n8n(f"/api/v1/workflows/{WF2}")
W2_ORIG = copy.deepcopy(w2)
w2n = {n["name"]: n for n in w2["nodes"]}
retry_changes = []
for nm in PD_NODES:
    n = w2n.get(nm)
    if not n or not n["type"].endswith("httpRequest"):
        continue
    before = (n.get("retryOnFail"), n.get("maxTries"), n.get("waitBetweenTries"))
    if before == (True, RETRY["maxTries"], RETRY["waitBetweenTries"]):
        continue
    n.update(RETRY)
    retry_changes.append((nm, before))

print("\n--- planned ---")
print(f"  WF-2S Replay Into WF-2 -> batchSize 1, interval {SPACING_MS}ms  "
      f"({'CHANGE' if ws_change else 'already set'})")
print(f"  WF-2 Pipedrive nodes -> retry 5x @5s  ({len(retry_changes)} nodes)")
for nm, b in retry_changes:
    print(f"     {nm:<22} was retryOnFail={b[0]} maxTries={b[1]} wait={b[2]}")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for tag, orig in (("wf2s", WS_ORIG), ("wf2", W2_ORIG)):
    with open(os.path.join(HERE, f"{tag}_backup_before_spacing_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(orig, indent=2, ensure_ascii=False))

for wid, wfobj, label in ((WF2S, ws, "WF-2S"), (WF2, w2, "WF-2")):
    d = stripped_keys(wfobj)
    if d:
        print(f"  {label}: stripping UI-only settings keys: {d}")
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(wfobj))

after_s = n8n(f"/api/v1/workflows/{WF2S}")
after_2 = n8n(f"/api/v1/workflows/{WF2}")
asn = {n["name"]: n for n in after_s["nodes"]}
a2n = {n["name"]: n for n in after_2["nodes"]}
b = ((asn["Replay Into WF-2"]["parameters"].get("options") or {}).get("batching") or {})
problems = []
if (b.get("batch") or {}).get("batchInterval") != SPACING_MS:
    problems.append(f"batching not stored as expected: {json.dumps(b)}")
for nm, _ in retry_changes:
    n = a2n.get(nm) or {}
    if n.get("maxTries") != RETRY["maxTries"] or n.get("waitBetweenTries") != RETRY["waitBetweenTries"]:
        problems.append(f"{nm}: retry not applied ({n.get('maxTries')}/{n.get('waitBetweenTries')})")
for w, tag, orig in ((after_s, "WF-2S", WS_ORIG), (after_2, "WF-2", W2_ORIG)):
    if w.get("active") is not orig.get("active"):
        problems.append(f"{tag} active={w.get('active')}")
    if len(w["nodes"]) != len(orig["nodes"]):
        problems.append(f"{tag} node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2S versionId={after_s.get('versionId')} active={after_s.get('active')} "
      f"batching={json.dumps(b)}")
print(f"  WF-2  versionId={after_2.get('versionId')} active={after_2.get('active')} "
      f"nodes={len(after_2['nodes'])}")
print("\nNOTE: batching read-back proves STORAGE, not EFFECT. The wire test is the next WF-2S")
print("cycle: consecutive WF-2 executions should start ~10s apart, not within the same second.")
sys.exit(1 if problems else 0)
