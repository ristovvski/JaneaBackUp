#!/usr/bin/env python3
"""Controlled alarm firing: make a TRUE condition trip immediately, observe the Slack post on the
wire, then restore config and verify by read-back.

    python fire_alarm_controlled.py WF-2R wf2s_stale_minutes 1 "Ops Warn WF-2S Stale"

Deliberately NOT faking data: the threshold is lowered so a genuinely-true condition trips. The
alarm reports something real, just sooner - which is what makes it a valid test of the alarm rather
than of a fixture.

Success = the Slack node returned ok:true with a ts. 'The node ran' is not success; that is exactly
the error that let 25 broken alert posts look healthy for eleven days.

RESTORE IS GUARANTEED - it runs in a finally block and is confirmed by an independent re-read.
"""
import json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = {"WF-2": "jp7rum9Z0YDJkQWv", "WF-2S": "6Y92ryBwYoy6z0Jx", "WF-2R": "U8Bb7Pdq7S6nzYPa"}


def n8n(path, method="GET", body=None, q=None):
    """method stays positional-2 to match the deploy scripts; query params are their OWN kwarg.
    Passing a dict as the 2nd arg (the habit from the read-only helpers) makes urllib try to use
    it as the HTTP verb, which is how this script crashed on its first run."""
    if isinstance(method, dict):
        raise TypeError("pass query params as q=..., not as the method argument")
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def set_keys(wfk, pairs):
    """pairs: {config_key: value}. Returns the previous values."""
    wid = IDS[wfk]
    wf = n8n(f"/api/v1/workflows/{wid}")
    node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
    cfg = json.loads(node["parameters"]["jsonOutput"])
    prev = {k: cfg.get(k) for k in pairs}
    cfg.update(pairs)
    node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
    was = wf.get("active")
    if was:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(wf))
    if was:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    after = n8n(f"/api/v1/workflows/{wid}")
    acfg = json.loads(next(n for n in after["nodes"]
                           if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    for k, v in pairs.items():
        if acfg.get(k) != v:
            raise SystemExit(f"config write did not take: {k}={acfg.get(k)!r} expected {v!r}")
    return prev, after.get("active")


if len(sys.argv) < 5:
    print("usage: fire_alarm_controlled.py <WF> <config_key> <temp_value> <slack node> "
          "[more_key=val ...]")
    sys.exit(2)
wfk, key, val, slack_node = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
pairs = {key: int(val) if str(val).lstrip("-").isdigit() else val}
for extra in sys.argv[5:]:
    k, v = extra.split("=", 1)
    pairs[k] = int(v) if v.lstrip("-").isdigit() else v

wid = IDS[wfk]
start = datetime.now(timezone.utc)
print(f"FIRE {wfk}/{slack_node}  via {pairs}  at {start.isoformat()}")

seen = n8n("/api/v1/executions", q={"workflowId": wid, "limit": 3})
before_ids = {e["id"] for e in (seen.get("data") or [])}

prev = None
result = {"fired": False}
try:
    prev, active = set_keys(wfk, pairs)
    print(f"  config set (was {prev}), active={active}")
    print("  waiting for the next scheduled cycle (up to 20 min)...", flush=True)
    deadline = time.time() + 20 * 60
    while time.time() < deadline and not result["fired"]:
        d = n8n("/api/v1/executions", q={"workflowId": wid, "limit": 5})
        for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
            if e["id"] in before_ids:
                continue
            det = n8n(f"/api/v1/executions/{e['id']}", q={"includeData": "true"})
            rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
            if slack_node not in rd:
                print(f"    cycle {e['id']} ran but {slack_node} did not fire "
                      f"(condition not met yet)", flush=True)
                before_ids.add(e["id"])
                continue
            try:
                j = rd[slack_node][0]["data"]["main"][0][0]["json"]
            except Exception:
                j = {}
            result = {"fired": True, "exec": e["id"], "at": e.get("startedAt"),
                      "ok": j.get("ok"), "channel": j.get("channel"),
                      "ts": (j.get("message") or {}).get("ts") if isinstance(j.get("message"), dict)
                            else j.get("ts"),
                      "error": j.get("error"),
                      "text": (j.get("message") or {}).get("text")
                              if isinstance(j.get("message"), dict) else None}
            break
        if not result["fired"]:
            time.sleep(45)
finally:
    if prev is not None:
        try:
            set_keys(wfk, prev)
            back = n8n(f"/api/v1/workflows/{wid}")
            bcfg = json.loads(next(n for n in back["nodes"]
                                   if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
            ok_restore = all(bcfg.get(k) == v for k, v in prev.items())
            print(f"\n  RESTORED {prev} -> verified={ok_restore} active={back.get('active')}")
            result["restored"] = ok_restore
        except Exception as e:
            print(f"\n  *** RESTORE FAILED: {str(e)[:200]} - restore {prev} MANUALLY ***")
            result["restored"] = False

print("\n--- RESULT ---")
print(json.dumps({k: (str(v)[:120] if isinstance(v, str) else v)
                  for k, v in result.items()}, indent=2, default=str))
posted = result.get("fired") and result.get("ok") is True and result.get("ts")
print(f"\n{wfk}/{slack_node}: "
      f"{'PROVEN - posted with ok:true and a ts' if posted else 'NOT PROVEN'}")
path = os.path.join(HERE, "wf1-release-evidence",
                    f"fire_{slack_node.replace(' ', '_')}.json")
json.dump(result, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if posted else 1)

