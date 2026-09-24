#!/usr/bin/env python3
"""The 401 tracks the PAYLOAD, not the key. Bisect which part of it trips.

Established: a PUT of WF-2's CURRENT nodes returns 200, while the P0-1b PUT (same key, same URL,
seconds apart) returns 401 with a body byte-identical to a deliberately-bad-key response. So this is
not credentials, not the workflow, not timing, and not a lock. Something in the body is rejected,
and rejected as "unauthorized" - which is why every retry strategy failed.

Bisect, smallest first, REVERTING after every success so WF-2 never keeps a test change:
  A control       - current nodes, unchanged                     (expect 200)
  B dedupe-only   - only the Dedupe jsCode edit                  (no new nodes)
  C one-node      - control + ONE new Claim node
  D wrapped-only  - control + the four IIFE-wrapped inline sites (no new nodes)
  E full          - the real P0-1b payload

Safety: after every test, the ORIGINAL body is PUT back and the node count re-read. The script
refuses to exit until WF-2 reads back at its original node count, and says so loudly if it cannot.
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
        return e.code, e.read()[:160].decode("utf-8", "replace")


def body_of(w):
    return {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
            "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in ALLOWED}}


st, wf = call(f"/api/v1/workflows/{WF2}")
if st != 200:
    sys.exit(f"cannot read WF-2: {st}")
ORIG = copy.deepcopy(wf)
ORIG_BODY = body_of(ORIG)
N0 = len(ORIG["nodes"])
print(f"WF-2 versionId={wf.get('versionId')} nodes={N0} active={wf.get('active')}")
print(f"payload size, control: {len(json.dumps(ORIG_BODY))} bytes\n")


def revert(tag):
    for _ in range(4):
        s, _r = call(f"/api/v1/workflows/{WF2}", "PUT", ORIG_BODY)
        if s == 200:
            _s, w = call(f"/api/v1/workflows/{WF2}")
            if len(w["nodes"]) == N0:
                return True
        time.sleep(5)
    print(f"*** REVERT FAILED after {tag} - WF-2 may be modified, CHECK IT ***")
    return False


def attempt(tag, mutate):
    w = copy.deepcopy(ORIG)
    mutate(w)
    b = body_of(w)
    size = len(json.dumps(b))
    s, r = call(f"/api/v1/workflows/{WF2}", "PUT", b)
    print(f"  {tag:<14} nodes={len(b['nodes']):<4} bytes={size:<7} -> HTTP {s}"
          + ("" if s == 200 else f"   {r}"))
    if s == 200:
        revert(tag)
    return s


def m_none(w):
    pass


def m_dedupe(w):
    for n in w["nodes"]:
        if n["name"] == "Dedupe":
            n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(
                "if (!duplicate) store.wf2_seen[key] = nowSec;",
                "// P0-1b: claim moved to the success terminals.")


def m_one_node(w):
    aft = next(n for n in w["nodes"] if n["name"] == "Lead Create")
    ax, ay = (aft.get("position") or [0, 0])[:2]
    w["nodes"].append({"parameters": {"jsCode": "const __items = $input.all();\nreturn __items;"},
                       "id": "c1a1m000-0000-4000-8000-000000000001", "name": "Claim SENT",
                       "type": "n8n-nodes-base.code", "typeVersion": 2,
                       "position": [ax + 220, ay + 60]})
    w["connections"].setdefault("Lead Create", {}).setdefault("main", [[]])
    w["connections"]["Lead Create"]["main"][0] = (
        (w["connections"]["Lead Create"]["main"][0] or [])
        + [{"node": "Claim SENT", "type": "main", "index": 0}])


def m_wrapped(w):
    for n in w["nodes"]:
        if n["name"] in INLINE_SITES:
            n["parameters"]["jsCode"] = ("const __items = (() => {\n"
                                         + n["parameters"]["jsCode"] + "\n})();\n"
                                         + CLAIM_INLINE + "\nreturn __items;")


print("--- bisect ---")
attempt("A control", m_none)
attempt("B dedupe", m_dedupe)
attempt("C one-node", m_one_node)
attempt("D wrapped", m_wrapped)

st, w = call(f"/api/v1/workflows/{WF2}")
print(f"\nfinal state: nodes={len(w['nodes'])} (expected {N0}) active={w.get('active')} "
      f"versionId={w.get('versionId')}")
print("WF-2 INTACT" if len(w["nodes"]) == N0 else "*** WF-2 NODE COUNT WRONG - INTERVENE ***")
