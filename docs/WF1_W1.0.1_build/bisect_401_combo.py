#!/usr/bin/env python3
"""Each P0-1b element PUTs fine alone; the full payload 401s. Find the boundary.

Control 199,952 bytes -> 200. Wrapped 201,076 -> 200. The full change is ~202-203k. So the next
question is simply: is this cumulative SIZE, or one specific combination? Build up in steps and
print bytes against status. Reverts to the original after every successful step; refuses to finish
until WF-2 reads back at 145 nodes.
"""
import copy, json, os, ssl, sys, time, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
ALLOWED = ("executionOrder", "errorWorkflow", "saveDataSuccessExecution",
           "saveDataErrorExecution", "saveManualExecutions", "saveExecutionProgress",
           "executionTimeout", "timezone")
CLAIM_INLINE = """
try {
  const __k = $('Dedupe').item.json.__dedupe_key;
  if (__k) {
    const __sd = $getWorkflowStaticData('global');
    (__sd.wf2_seen = __sd.wf2_seen || {})[__k] = Math.floor(Date.now() / 1000);
  }
} catch (e) { }
"""
INLINE_SITES = ["NoOp Lead Exists", "NoOp Nurture SENT", "NoOp Repeat SENT", "Reply CRM Done"]
CLAIMS = [("Claim SENT", "Lead Create"), ("Claim Bounce", "Bounce Note"),
          ("Claim Unsub", "U Lead DNC Label"), ("Claim Nurture", "Nurture Alert")]


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY,
                                        "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:120].decode("utf-8", "replace")


def body_of(w):
    return {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
            "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in ALLOWED}}


st, wf = call(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
ORIG_BODY = body_of(ORIG)
N0 = len(ORIG["nodes"])
print(f"WF-2 nodes={N0} versionId={wf.get('versionId')}\n")


def revert():
    for _ in range(4):
        s, _ = call(f"/api/v1/workflows/{WF2}", "PUT", ORIG_BODY)
        if s == 200:
            _s, w = call(f"/api/v1/workflows/{WF2}")
            if len(w["nodes"]) == N0:
                return True
        time.sleep(5)
    return False


def build(n_claims, wrapped, dedupe, pad=0):
    w = copy.deepcopy(ORIG)
    if dedupe:
        for n in w["nodes"]:
            if n["name"] == "Dedupe":
                n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(
                    "if (!duplicate) store.wf2_seen[key] = nowSec;", "// moved")
    if wrapped:
        for n in w["nodes"]:
            if n["name"] in INLINE_SITES:
                n["parameters"]["jsCode"] = ("const __items = (() => {\n"
                                             + n["parameters"]["jsCode"] + "\n})();\n"
                                             + CLAIM_INLINE + "\nreturn __items;")
    for i, (nm, aft) in enumerate(CLAIMS[:n_claims]):
        a = next(x for x in w["nodes"] if x["name"] == aft)
        ax, ay = (a.get("position") or [0, 0])[:2]
        w["nodes"].append({"parameters": {"jsCode": CLAIM_INLINE + "\nreturn $input.all();"
                                          + ("\n// " + "x" * pad if pad else "")},
                           "id": f"c1a1m000-0000-4000-8000-00000000000{i + 1}", "name": nm,
                           "type": "n8n-nodes-base.code", "typeVersion": 2,
                           "position": [ax + 220, ay + 60]})
        w["connections"].setdefault(aft, {}).setdefault("main", [[]])
        w["connections"][aft]["main"][0] = ((w["connections"][aft]["main"][0] or [])
                                            + [{"node": nm, "type": "main", "index": 0}])
    return w


def attempt(tag, w):
    b = body_of(w)
    size = len(json.dumps(b))
    s, r = call(f"/api/v1/workflows/{WF2}", "PUT", b)
    print(f"  {tag:<34} nodes={len(b['nodes']):<4} bytes={size:<7} -> HTTP {s}"
          + ("" if s == 200 else f"  {r}"))
    if s == 200:
        revert()
    return s, size


print("--- building up ---")
attempt("dedupe+wrapped", build(0, True, True))
for k in (1, 2, 3, 4):
    attempt(f"dedupe+wrapped+{k} claim node(s)", build(k, True, True))

print("\n--- size probe: control + padding only (no new behaviour) ---")
for pad in (0, 1000, 2000, 4000):
    w = build(1, False, False, pad=pad)
    attempt(f"1 node + {pad}b padding", w)

st, w = call(f"/api/v1/workflows/{WF2}")
print(f"\nfinal: nodes={len(w['nodes'])} (expected {N0}) active={w.get('active')}")
print("WF-2 INTACT" if len(w["nodes"]) == N0 else "*** NODE COUNT WRONG - INTERVENE ***")
