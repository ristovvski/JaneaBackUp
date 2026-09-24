#!/usr/bin/env python3
"""Verify the #26 cutover against CODE, not comment prose.

My post-deploy assertion flagged 'gate still reads staticData' and 'Labels Compute still writes
staticData'. Both matched text inside the new COMMENTS - the gate's comment explains what
$getWorkflowStaticData does wrong, and the replacement block names __alerted_v1 as the rollback
copy. Same false-alarm class as the earlier index('__skip:') hit. Strip comments, then assert.
"""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def code_only(js):
    out = []
    for line in js.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        out.append(re.sub(r"//.*$", "", line))
    return "\n".join(out)


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print(f"WF-1 versionId {wf.get('versionId')}  nodes={len(wf['nodes'])}  active={wf.get('active')}")

gate = code_only(N["M7 Alert Gate"]["parameters"]["jsCode"])
lc = code_only(N["M7 Labels Compute"]["parameters"]["jsCode"])
checks = [
    ("gate does NOT call getWorkflowStaticData", "getWorkflowStaticData" not in gate),
    ("gate does NOT touch __alerted_v1", "__alerted_v1" not in gate),
    ("gate reads the dataTable result", "family === 'wf1_alert'" in gate),
    ("gate checks the success shape POSITIVELY", "claimed_at" in gate and "isRow" in gate),
    ("gate keeps the fail-open branch", "dt_unavailable_fail_open" in gate),
    ("gate keeps manual_conversation", "manual_conversation" in gate),
    ("gate keeps the legacy-key branch", "already_delivered_legacy_lead_key" in gate),
    ("Labels Compute does NOT call getWorkflowStaticData",
     "getWorkflowStaticData" not in lc),
    ("Labels Compute does NOT write __alerted_v1", "__alerted_v1" not in lc),
    ("Labels Compute still returns its items", "return __items;" in lc),
]
for nm in ("M7 Alert Key", "M7 DT Alert Get", "M7 IF Alert Delivered", "M7 DT Alert Claim"):
    checks.append((f"node present: {nm}", nm in N))
checks.append(("DT Get is non-blocking",
               N.get("M7 DT Alert Get", {}).get("onError") == "continueRegularOutput"))
checks.append(("DT Get uses anyCondition (one query, no Merge barrier)",
               N.get("M7 DT Alert Get", {}).get("parameters", {}).get("matchType")
               == "anyCondition"))
bo = [c.get("node") for g in (C.get("M7 Build") or {}).get("main", []) for c in (g or [])]
so = [c.get("node") for g in (C.get("M7 Critical Slack") or {}).get("main", []) for c in (g or [])]
checks.append(("M7 Build -> M7 Alert Key", bo == ["M7 Alert Key"]))
checks.append(("Critical Slack fans to both IF Patch and IF Alert Delivered",
               "M7 IF Patch" in so and "M7 IF Alert Delivered" in so))

print()
bad = 0
for label, good in checks:
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    bad += 0 if good else 1
print(f"\nVERDICT: {'CLEAN' if bad == 0 else f'{bad} PROBLEM(S)'}")

sd = wf.get("staticData") or {}
if isinstance(sd, str):
    sd = json.loads(sd)
reg = ((sd.get("global") or {}).get("__alerted_v1") or {})
print(f"\nrollback copy still present in staticData: {len(reg)} keys "
      f"(intentional until a live multi-event second proves the port)")
