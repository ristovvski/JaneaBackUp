#!/usr/bin/env python3
"""B3 - THE FLIP. WRITE_MODE shadow -> live, WITHOUT arming the webhook secret.

Secret deliberately NOT armed: WF-2's Verify Secret reads a BODY secret_key, the reconcilers send
none, and the X-Replay-Auth path was never built - arming today would silently drop every WF-2S /
WF-2R replay. Named follow-up, first post-flip task.

Sequence, exactly as gated:
  pause WF-2S + WF-2R -> WRITE_MODE=live -> deploy -> read-back active===true + webhook probe 200
  -> unpause -> verify one reconciler replay still authenticates

Unpause runs in a finally block. A failed flip must not leave the safety nets dead.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
POLLERS = {"WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}
WEBHOOK = "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def probe(payload):
    try:
        r = urllib.request.Request(WEBHOOK, data=json.dumps(payload).encode(), method="POST",
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
            return x.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)[:80]


stamp = datetime.now(timezone.utc)
print(f"B3 START {stamp.isoformat()}")

before = n8n(f"/api/v1/workflows/{WF2}")
bcfg = json.loads(next(n for n in before["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
print(f"WF-2 before: active={before.get('active')} versionId={before.get('versionId')} "
      f"WRITE_MODE={bcfg.get('WRITE_MODE')} secret_armed={bool(bcfg.get('webhook_secret_sha256'))}")
if bcfg.get("WRITE_MODE") == "live":
    print("already live - nothing to do")
    sys.exit(0)

backup = os.path.join(HERE, f"wf2_backup_before_FLIP_{int(stamp.timestamp())}.json")
open(backup, "w", encoding="utf-8").write(json.dumps(before, indent=2, ensure_ascii=False))
print(f"ROLLBACK SNAPSHOT: {backup}")

was = {}
rc = 1
try:
    for name, wid in POLLERS.items():
        was[name] = n8n(f"/api/v1/workflows/{wid}").get("active")
        if was[name]:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
            still = n8n(f"/api/v1/workflows/{wid}").get("active")
            print(f"  paused {name}: active={still}")
            if still:
                raise SystemExit(f"{name} would not pause")

    wf = n8n(f"/api/v1/workflows/{WF2}")
    cfg_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
    cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
    cfg["WRITE_MODE"] = "live"
    # explicitly NOT arming: leave webhook_secret_sha256 as-is (null)
    cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)

    if wf.get("active"):
        n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
    d = stripped_keys(wf)
    if d:
        print(f"  stripping UI-only settings keys: {d}")
    n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
    n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})
    rc = 0
finally:
    for name, wid in POLLERS.items():
        if was.get(name):
            try:
                n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
                back = n8n(f"/api/v1/workflows/{wid}").get("active")
                print(f"  unpaused {name}: active={back}")
                if not back:
                    print(f"  *** {name} DID NOT COME BACK - reactivate manually ***")
            except Exception as e:
                print(f"  *** {name} reactivation FAILED: {str(e)[:200]} ***")

after = n8n(f"/api/v1/workflows/{WF2}")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
st = probe({"event_type": "flip_b3_readback_probe"})

checks = {
    "WRITE_MODE==live": acfg.get("WRITE_MODE") == "live",
    "active===true": after.get("active") is True,
    "webhook probe 200": st == 200,
    "secret still unarmed (by design)": not acfg.get("webhook_secret_sha256"),
    "node count unchanged": len(after["nodes"]) == len(before["nodes"]),
    "owner_id preserved": acfg.get("owner_id") == bcfg.get("owner_id"),
    "forward map preserved": len(acfg.get("forward_inbox_map") or {})
                             == len(bcfg.get("forward_inbox_map") or {}),
    "WF-2S back": n8n(f"/api/v1/workflows/{POLLERS['WF-2S']}").get("active") is True,
    "WF-2R back": n8n(f"/api/v1/workflows/{POLLERS['WF-2R']}").get("active") is True,
}
print("\n--- B3 READ-BACK ---")
for k, v in checks.items():
    print(f"  [{'OK ' if v else 'RED'}] {k}")
print(f"  versionId: {after.get('versionId')}")
print(f"  webhook probe status: {st}")

ok = all(checks.values())
print(f"\nB3: {'GREEN - WF-2 IS LIVE' if ok else 'RED'}")
json.dump({"at": stamp.isoformat(), "checks": checks, "versionId": after.get("versionId"),
           "backup": backup, "probe_status": st},
          open(os.path.join(HERE, "wf1-release-evidence", "b3_flip_live.json"), "w",
               encoding="utf-8"), indent=2, default=str)
sys.exit(0 if ok else 1)
