#!/usr/bin/env python3
"""Seed F|<dedupe_key> for EVERY event we have already forwarded, so no armed replay can re-fire.

The duplicate forward is no longer a prediction: exec 15252 sent a SECOND forward for the fixture
at 13:45:56Z (wire: 4 replies / 5 forwards). The F-key gate is live as of 3068bce0, but every event
forwarded BEFORE it went in is still unprotected - and several have had their main dedupe key
released for replay, which is exactly an armed canary.

MAPPING AUTHORITY. Nik said "seed from Smartlead forward history". Smartlead is the authority on
what was SENT, but it cannot tell me the dedupe key, and reconstructing one from its timestamps
would run straight into the ISO-vs-RFC-2822 trap in section 9b. So:
  * n8n executions give the exact pairing (SL Forward Email ok:true  ->  Dedupe.__dedupe_key)
  * Smartlead FORWARD history is then used as the CROSS-CHECK on the count
If Smartlead shows more forwards than executions can account for, that gap is REPORTED, not papered
over - an unmappable forward is one we cannot protect, and pretending otherwise is worse than
knowing.

Seeded with NOW, not with the original forward time: `Dedupe` prunes entries older than
dedupe_max_age_sec (48h), so a key stamped with an old time would be swept immediately and protect
nothing. 48h forward is also exactly WF-2R's replay reach, so the protection covers the window in
which a replay is possible at all.

Marine is deliberately NOT pre-seeded: her forward has not happened yet. With the gate live it will
fire ONCE and claim itself on success - which is the recovery we actually want.
"""
import argparse, json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
SLK = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"


def n8n(p, q=None, method="GET", body=None, attempt=0):
    import time
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(p, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {p} FAILED: HTTP {e.code}")


def sl(p, q=None):
    qq = dict(q or {})
    qq["api_key"] = SLK
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://server.smartlead.ai/api/v1{p}?{urllib.parse.urlencode(qq)}",
                headers={"User-Agent": "janea/1.0"}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   smartlead read failed: {str(e)[:110]}")
        return None


def node(rd, nm):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception:
        return None


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

print("walking WF-2 executions for forwards that actually SENT...")
ids, cursor = [], None
while True:
    q = {"workflowId": WF2, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += [e["id"] for e in (p.get("data") or [])]
    cursor = p.get("nextCursor")
    if not cursor:
        break
print(f"  executions to inspect: {len(ids)}")

forwarded, unmappable, inspected = {}, [], 0
for i, eid in enumerate(ids, 1):
    det = n8n(f"/api/v1/executions/{eid}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    inspected += 1
    fwd = node(rd, "SL Forward Email")
    if not fwd or fwd.get("ok") is not True:
        continue
    ded = node(rd, "Dedupe") or {}
    dk = ded.get("__dedupe_key")
    nm = node(rd, "Normalize") or {}
    who = (nm.get("lead") or {}).get("email")
    if not dk:
        unmappable.append((eid, who))
        continue
    forwarded.setdefault(dk, []).append((eid, who, fwd.get("messageId")))

print(f"  inspected {inspected}; executions with a SUCCESSFUL forward: "
      f"{sum(len(v) for v in forwarded.values())}")
print(f"  distinct dedupe keys forwarded: {len(forwarded)}")
print(f"  forwards with no dedupe key (unmappable): {len(unmappable)}")
for k, v in forwarded.items():
    if len(v) > 1:
        print(f"  *** DUPLICATE FORWARD on {k}: {[x[0] for x in v]} ({v[0][1]}) ***")
for eid, who in unmappable:
    print(f"      unmappable: exec {eid} {who}")

print("\ncross-check against the Smartlead wire (authority on what was SENT)")
camps = sl("/campaigns") or []
camps = camps if isinstance(camps, list) else (camps.get("data") or [])
active = [c for c in camps if str(c.get("status", "")).upper() in ("ACTIVE", "START", "RUNNING")]
wire_fwd = 0
for c in active:
    st = sl(f"/campaigns/{c.get('id')}/leads-statistics", {"limit": 100})
    for r in ((st or {}).get("data") or []):
        for h in (r.get("history") or []):
            if str(h.get("type", "")).upper() == "FORWARD":
                wire_fwd += 1
print(f"  FORWARD entries on the wire (active campaigns): {wire_fwd}")
print(f"  forwards we can map to a dedupe key: {sum(len(v) for v in forwarded.values())}")
if wire_fwd > sum(len(v) for v in forwarded.values()):
    print(f"  NOTE: {wire_fwd - sum(len(v) for v in forwarded.values())} wire forward(s) are not "
          f"accounted for by our executions - they CANNOT be seeded, and are reported rather than "
          f"assumed harmless (older than execution retention, or sent by Make pre-flip).")

wf = n8n(f"/api/v1/workflows/{WF2}")
sd = (wf.get("staticData") or {}).get("global") or {}
seen = dict(sd.get("wf2_seen") or {})
now = int(datetime.now(timezone.utc).timestamp())
to_seed = {f"F|{k}": now for k in forwarded if f"F|{k}" not in seen}
print(f"\n--- planned ---")
print(f"  existing F-keys : {[k for k in seen if k.startswith('F|')]}")
print(f"  F-keys to seed  : {len(to_seed)}")
for k in to_seed:
    print(f"     {k}")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)
if not to_seed:
    print("\nnothing to seed."); sys.exit(0)

fresh = ((n8n(f"/api/v1/workflows/{WF2}").get("staticData") or {}).get("global") or {})
fseen = dict(fresh.get("wf2_seen") or {})
fseen.update(to_seed)
body = put_body(wf)
body["staticData"] = {"global": {**fresh, "wf2_seen": fseen}}
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2}", None, "PUT", body)

after = n8n(f"/api/v1/workflows/{WF2}")
aseen = ((after.get("staticData") or {}).get("global") or {}).get("wf2_seen") or {}
missing = [k for k in to_seed if k not in aseen]
print(f"\nlive verification: {'CLEAN' if not missing else 'PROBLEMS'}")
for k in missing:
    print(f"  - not seeded: {k}")
print(f"  versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
print(f"  wf2_seen={len(aseen)}  F-keys={sorted(k for k in aseen if k.startswith('F|'))}")
sys.exit(1 if missing else 0)
