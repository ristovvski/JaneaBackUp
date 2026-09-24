#!/usr/bin/env python3
"""Generic deploy-window wrapper: pause the reconcilers, run a patch script, unpause.

    python deploy_with_pollers_paused.py patch_wf2_alert_text.py --deploy

Both reconcilers POST into WF-2's webhook, so a WF-2 deploy window makes their replays 404. That
is survivable (claim-after-success leaves them retryable) but it burns a cycle and muddies the
evidence. Unpause runs in a finally block - a failed patch must never leave the safety nets dead,
which is the exact shape of the outage this whole week has been about.
"""
import json, os, ssl, subprocess, sys, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
POLLERS = {"WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


if len(sys.argv) < 2:
    print("usage: deploy_with_pollers_paused.py <script.py> [args...]")
    sys.exit(2)
script, extra = sys.argv[1], sys.argv[2:]

was, rc = {}, 1
try:
    for name, wid in POLLERS.items():
        was[name] = n8n(f"/api/v1/workflows/{wid}").get("active")
        if was[name]:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
            still = n8n(f"/api/v1/workflows/{wid}").get("active")
            print(f"paused {name}: active={still}")
            if still:
                raise SystemExit(f"{name} would not pause - aborting before the patch")
    print(f"\n--- running {script} {' '.join(extra)} ---")
    p = subprocess.run([sys.executable, os.path.join(HERE, script)] + extra,
                       capture_output=True, text=True, cwd=HERE)
    print(p.stdout[-3000:])
    if p.stderr.strip():
        print("stderr:", p.stderr[-800:])
    rc = p.returncode
finally:
    for name, wid in POLLERS.items():
        if was.get(name):
            try:
                n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
                back = n8n(f"/api/v1/workflows/{wid}").get("active")
                print(f"unpaused {name}: active={back}")
                if not back:
                    print(f"*** {name} DID NOT COME BACK - reactivate manually ***")
            except Exception as e:
                print(f"*** {name} reactivation FAILED: {str(e)[:200]} ***")
print(f"\nwrapper exit: {rc}")
sys.exit(rc)
