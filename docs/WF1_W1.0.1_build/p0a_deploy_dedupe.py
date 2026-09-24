#!/usr/bin/env python3
"""P0a - deploy the WF-2 Dedupe canonicalisation under the deploy-window rule.

pause WF-2S + WF-2R  ->  patch WF-2  ->  read-back  ->  unpause

The pause matters: both reconcilers POST into WF-2's webhook. With WF-2 deactivated their replays
would 404. That is survivable (both use claim-after-success, so a rejected replay stays retryable)
but it burns a cycle and muddies the flip evidence, so they are stopped first.

UNPAUSE IS GUARANTEED. The reactivation runs in a finally block - a failed patch must not leave the
reconcilers dead, which is exactly the shape of the outage this whole day has been about.
"""
import json, os, ssl, subprocess, sys, urllib.error, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
POLLERS = {"WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}
WF2 = "jp7rum9Z0YDJkQWv"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


was = {}
for name, wid in POLLERS.items():
    was[name] = n8n(f"/api/v1/workflows/{wid}").get("active")
    print(f"{name}: active={was[name]}")

rc = 1
try:
    for name, wid in POLLERS.items():
        if was[name]:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
            still = n8n(f"/api/v1/workflows/{wid}").get("active")
            print(f"  paused {name} -> active={still}")
            if still:
                print(f"REFUSING: {name} would not pause")
                raise SystemExit(2)

    print("\n--- deploying WF-2 dedupe canonicalisation ---")
    p = subprocess.run([sys.executable, os.path.join(HERE, "patch_wf2_dedupe_canon.py"),
                        "--deploy"], capture_output=True, text=True, cwd=HERE)
    print(p.stdout[-2500:])
    if p.stderr.strip():
        print("stderr:", p.stderr[-800:])
    rc = p.returncode
finally:
    for name, wid in POLLERS.items():
        if was.get(name):
            try:
                n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
                back = n8n(f"/api/v1/workflows/{wid}").get("active")
                print(f"  unpaused {name} -> active={back}")
                if not back:
                    print(f"  *** {name} DID NOT COME BACK - manual reactivation required ***")
            except Exception as e:
                print(f"  *** {name} reactivation FAILED: {str(e)[:200]} ***")

# independent read-back of the thing we actually changed
live = n8n(f"/api/v1/workflows/{WF2}")
ded = next(n for n in live["nodes"] if n["name"] == "Dedupe")["parameters"]["jsCode"]
print(f"\nWF-2 read-back: active={live.get('active')} versionId={live.get('versionId')} "
      f"nodes={len(live['nodes'])}")
print(f"  Dedupe keys on epoch ms: {'__ts' in ded}")
cfg = json.loads(next(n for n in live["nodes"]
                      if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
print(f"  WRITE_MODE still: {cfg.get('WRITE_MODE')}  (must still be shadow at P0a)")
ok = ("__ts" in ded) and live.get("active") is True and cfg.get("WRITE_MODE") == "shadow"
print(f"\nP0a: {'GREEN' if ok else 'RED'}")
sys.exit(0 if ok else 1)
