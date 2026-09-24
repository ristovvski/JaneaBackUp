#!/usr/bin/env python3
"""URGENT restore - WF-2S thresholds left at 0 by a controlled fire whose finally block never ran.

The fire process stalled past its deadline without restoring, so the alarm has been screaming
'live window overdue' every cycle against a threshold of 0. Restore the captured previous values
and verify by independent read-back.

Previous values, from the fire's own log:  wf2h_stale_hours 48 · write_mode_max_hours 2
"""
import json, os, ssl, sys, urllib.request

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2S = "6Y92ryBwYoy6z0Jx"
WANT = {"wf2h_stale_hours": 48, "write_mode_max_hours": 2}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


wf = n8n(f"/api/v1/workflows/{WF2S}")
node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
cfg = json.loads(node["parameters"]["jsonOutput"])
print("before:", {k: cfg.get(k) for k in WANT})
if all(cfg.get(k) == v for k, v in WANT.items()):
    print("already restored - nothing to do")
    sys.exit(0)

cfg.update(WANT)
node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2S}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print("stripping UI-only settings keys:", d)
n8n(f"/api/v1/workflows/{WF2S}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF2S}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2S}")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
got = {k: acfg.get(k) for k in WANT}
ok = got == WANT and after.get("active") is was
print("after :", got)
print(f"active={after.get('active')} versionId={after.get('versionId')}")
print("RESTORE", "CLEAN" if ok else "FAILED")
sys.exit(0 if ok else 1)
