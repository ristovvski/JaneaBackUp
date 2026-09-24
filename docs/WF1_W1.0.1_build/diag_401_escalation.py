#!/usr/bin/env python3
"""Evidence pack for the n8n 401 escalation. Captures, never infers.

The auditor's asks, plus the checks that would embarrass us if support asked first:

  1. Literal id in OUR write path, byte for byte (his read says the real id ends kQWv). A miscased
     id is already excluded as a THEORY - it 404s, not 401s - but the literal is still worth printing.
  2. Full 401 body + headers from a real write, versus a deliberately BAD key. If the two bodies or
     headers differ, the key is not the problem, and that is the single most useful line in a ticket.
  3. Stale versionId in the payload. Normally 400/409 rather than 401, but excluded explicitly:
     one PUT with the versionId we hold, one with it stripped entirely.
  4. Control: the same PUT shape against a throwaway workflow we own. If that succeeds while WF-2
     fails, the problem is scoped to the workflow, not to the key, the payload, or the endpoint.

Writes NOTHING to WF-2 that could stick: every WF-2 PUT here sends the workflow's CURRENT nodes,
so if one unexpectedly succeeds, it is a no-op re-save rather than a surprise deploy.
"""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
ALLOWED = ("executionOrder", "errorWorkflow", "saveDataSuccessExecution",
           "saveDataErrorExecution", "saveManualExecutions", "saveExecutionProgress",
           "executionTimeout", "timezone")


def call(path, method="GET", body=None, key=KEY, label=""):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": key,
                                        "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            print(f"  [{method} {path[:46]:<46}] HTTP {x.status}   {label}")
            return x.status, json.load(x), dict(x.headers)
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        body_txt = e.read()[:300].decode("utf-8", "replace")
        keep = {k: v for k, v in hdrs.items()
                if k in ("server", "date", "content-type", "www-authenticate", "x-request-id",
                         "cf-ray", "retry-after") or "rate" in k or "limit" in k}
        print(f"  [{method} {path[:46]:<46}] HTTP {e.code}   {label}")
        print(f"      body   : {body_txt}")
        print(f"      headers: {json.dumps(keep)}")
        return e.code, None, hdrs


print("1. THE LITERAL ID IN OUR WRITE PATH")
print(f"   WF2 = {WF2!r}   len={len(WF2)}   endswith('kQWv')={WF2.endswith('kQWv')}")
print(f"   codepoints: {[hex(ord(c)) for c in WF2[-6:]]}  (last 6, to expose any homoglyph)")

print("\n2. READ (baseline)")
st, wf, _ = call(f"/api/v1/workflows/{WF2}", label="GET should be 200")
if not wf:
    raise SystemExit("cannot read WF-2 - stop here")
print(f"   versionId={wf.get('versionId')} active={wf.get('active')} nodes={len(wf['nodes'])}")

base = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}}

print("\n3. REAL KEY, unchanged payload (no-op re-save)")
real = call(f"/api/v1/workflows/{WF2}", "PUT", base, label="the failing call")

print("\n4. DELIBERATELY BAD KEY, same payload")
bad = call(f"/api/v1/workflows/{WF2}", "PUT", base, key="definitely-not-a-valid-key",
           label="if this differs from #3, the key is NOT the problem")

print("\n   COMPARISON")
print(f"   real-key status {real[0]}   bad-key status {bad[0]}   same_status={real[0] == bad[0]}")

print("\n5. STALE versionId excluded explicitly")
call(f"/api/v1/workflows/{WF2}", "PUT", {**base, "versionId": wf.get("versionId")},
     label="with the versionId we hold")
call(f"/api/v1/workflows/{WF2}", "PUT", {**base, "versionId": "00000000-0000-4000-8000-000000000000"},
     label="with a bogus versionId")

print("\n6. CONTROL: same shape against a throwaway workflow we create")
st, made, _ = call("/api/v1/workflows", "POST", {
    "name": "zz_401_control_DELETE_ME",
    "nodes": [{"parameters": {}, "id": "d1d1d1d1-0000-4000-8000-000000000001",
               "name": "NoOp", "type": "n8n-nodes-base.noOp", "typeVersion": 1,
               "position": [0, 0]}],
    "connections": {}, "settings": {"executionOrder": "v1"}}, label="create control")
if made and made.get("id"):
    cid = made["id"]
    call(f"/api/v1/workflows/{cid}", "PUT",
         {"name": made["name"], "nodes": made["nodes"], "connections": made["connections"],
          "settings": made.get("settings") or {}},
         label="PUT the control - succeeds => problem is scoped to WF-2")
    call(f"/api/v1/workflows/{cid}", "DELETE", label="cleanup")

print("\n7. OTHER WORKFLOWS, write endpoint (already known to work - recorded for the ticket)")
call("/api/v1/workflows/6Y92ryBwYoy6z0Jx/activate", "POST", {}, label="WF-2S activate (no-op)")
