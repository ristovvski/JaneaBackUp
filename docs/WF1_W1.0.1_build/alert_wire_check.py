#!/usr/bin/env python3
"""Wire-authoritative check of the REPLY ALERT on the fixed path, and produce the permalink.

b4b_resmoke grades `alert` as bool(rd.get('Reply Alert')) - node presence. That is exactly the
check that reported green while 25 consecutive posts failed. This one asserts the Slack API
response: ok === true AND a message ts, then renders the permalink.

Also cross-checks the channel actually received it, so the answer does not rest on the execution
record alone.
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
EMAIL = "pii-c61c7d08@example.invalid"
SINCE = os.environ.get("SINCE", "2026-08-10T14:30:00Z")
DEADLINE = datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get("WINDOW_MIN", "20")))


def n8n(p, q=None):
    u = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    r = urllib.request.Request(u, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        return json.load(x)


def g(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


print(f"waiting for a REPLIED execution for {EMAIL} after {SINCE}", flush=True)
hit = None
while datetime.now(timezone.utc) < DEADLINE and not hit:
    d = n8n("/api/v1/executions", q={"workflowId": WF2, "limit": 25})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
        if str(e.get("startedAt") or "") < SINCE:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", q={"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        if g(rd, "Normalize", "event") != "REPLIED":
            continue
        lead = g(rd, "Normalize", "lead") or {}
        if str(lead.get("email", "")).lower() != EMAIL:
            continue
        run = (rd.get("Reply Alert") or [{}])[0]
        try:
            j = run["data"]["main"][0][0]["json"]
        except Exception:
            j = {}
        msg = j.get("message") if isinstance(j.get("message"), dict) else {}
        hit = {"exec": e["id"], "at": e.get("startedAt"),
               "alert_node_ran": "Reply Alert" in rd,
               "ok": j.get("ok"), "channel": j.get("channel"),
               "ts": msg.get("ts") or j.get("ts"),
               "error": j.get("error") or run.get("error"),
               "text": msg.get("text"),
               "should_alert": g(rd, "First Reply Gate", "__should_alert"),
               "alert_reason": g(rd, "First Reply Gate", "__alert_reason"),
               "alert_text_built": bool(g(rd, "Body Reply Alert", "alert_text")),
               "category": g(rd, "Classify Parse", "__category"),
               "forward_to": g(rd, "Forward Resolve", "__forward_to")}
        break
    if not hit:
        time.sleep(30)

if not hit:
    print("no matching execution inside the window")
    sys.exit(2)

print("\n--- REPLY ALERT, WIRE AUTHORITY ---")
for k, v in hit.items():
    print(f"  {k}: {str(v)[:150]}")

posted = hit.get("ok") is True and bool(hit.get("ts"))
permalink = None
if posted:
    ts = str(hit["ts"]).replace(".", "")
    permalink = f"https://janea.slack.com/archives/{hit['channel']}/p{ts}"
    print(f"\nPERMALINK: {permalink}")
else:
    print(f"\nNOT POSTED — ok={hit.get('ok')!r} error={hit.get('error')!r}")
    print("  (node_ran was "
          f"{hit.get('alert_node_ran')} — which is exactly why node-presence is not evidence)")

print(f"\nREPLY ALERT: {'PROVEN ON THE WIRE' if posted else 'STILL BROKEN'}")
json.dump({**hit, "permalink": permalink},
          open(os.path.join(HERE, "wf1-release-evidence", "alert_wire_check.json"), "w",
               encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
sys.exit(0 if posted else 1)
