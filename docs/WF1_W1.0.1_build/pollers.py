#!/usr/bin/env python3
"""Pause/resume the reconcilers as a SEPARATE process from the deploy.

    python pollers.py pause
    python pollers.py resume

Why this exists: `deploy_with_pollers_paused.py` deactivates WF-2S and WF-2R and then immediately
runs the patch script, whose first state-changing call is WF-2's deactivate. That third state change
in quick succession returns HTTP 401 ("unauthorized") reproducibly - while the SAME call from a
separate process, a minute later, returns 200. Nearly 8 minutes of in-process backoff did not clear
it, so it is not a simple time window.

Splitting the state changes across processes, with a gap, keeps the deploy protocol (pollers paused
around the window) without tripping whatever is rejecting the burst.
"""
import json, os, ssl, sys, time, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
POLLERS = {"WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}


def call(path, method="GET", body=None, tries=4):
    for i in range(tries):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + path, method=method, data=data,
                                   headers={"X-N8N-API-KEY": KEY,
                                            "Content-Type": "application/json",
                                            "accept": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (401, 429, 502, 503) and i < tries - 1:
                print(f"   HTTP {e.code} on {method} {path[:48]} - wait 20s")
                time.sleep(20)
                continue
            raise
    raise SystemExit(f"gave up on {method} {path}")


action = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
if action not in ("pause", "resume"):
    sys.exit("usage: pollers.py pause|resume")
want_active = action == "resume"
for name, wid in POLLERS.items():
    cur = call(f"/api/v1/workflows/{wid}").get("active")
    if cur == want_active:
        print(f"{name}: already active={cur}")
        continue
    call(f"/api/v1/workflows/{wid}/{'activate' if want_active else 'deactivate'}", "POST", {})
    now = call(f"/api/v1/workflows/{wid}").get("active")
    print(f"{name}: active {cur} -> {now}")
    if now != want_active:
        sys.exit(f"*** {name} did not reach active={want_active} ***")
    time.sleep(5)
print(f"pollers {action}d")
