"""Step 0: reactivate WF-2 in shadow, and name WHY activate returned 200 without activating.

Root-cause candidates for "activate 200s but active stays false":
  C1 webhook PATH COLLISION - another active workflow owns the same path, so trigger registration
     fails while the API call itself succeeds
  C2 the activate call is accepted but n8n cannot register the trigger for another reason (bad
     credential on the trigger, disabled trigger node, unsupported trigger)
  C3 the call never happened / was made against the wrong id
Checked before touching anything, then activation is attempted and VERIFIED by re-reading state and
probing the live webhook - never by trusting the 200.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"


def api(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"X-N8N-API-KEY": KEY,
                                        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(r, timeout=180) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


print("=" * 96)
print("ROOT CAUSE - webhook path inventory across ALL workflows")
print("=" * 96)
paths = {}
wfs = []
cursor = None
while True:
    q = "/api/v1/workflows?limit=250" + (f"&cursor={cursor}" if cursor else "")
    st, d = api(q)
    if st >= 300:
        print(f"  workflow list failed: {st} {d}")
        break
    wfs.extend(d.get("data") or [])
    cursor = d.get("nextCursor")
    if not cursor:
        break
print(f"  workflows: {len(wfs)}")
for w in wfs:
    st, full = api(f"/api/v1/workflows/{w['id']}")
    if st >= 300:
        continue
    for n in (full.get("nodes") or []):
        if n["type"].endswith(".webhook"):
            p = (n.get("parameters") or {}).get("path") or n.get("webhookId")
            paths.setdefault(str(p), []).append(
                (full["id"], full.get("name"), full.get("active"), n.get("disabled", False)))

for p, owners in sorted(paths.items()):
    flag = ""
    active_owners = [o for o in owners if o[2]]
    if len(owners) > 1:
        flag = "  <<< SHARED PATH"
        if len(active_owners) > 1:
            flag = "  <<< COLLISION: two ACTIVE workflows claim this path"
    print(f"  path={p[:44]:<46}{flag}")
    for oid, nm, act, dis in owners:
        mark = " (THIS IS WF-2)" if oid == WF2 else ""
        print(f"      {oid}  active={act}  disabled_node={dis}  {str(nm)[:44]}{mark}")

wf2_paths = [p for p, o in paths.items() if any(x[0] == WF2 for x in o)]
collision = False
for p in wf2_paths:
    others = [x for x in paths[p] if x[0] != WF2]
    if any(x[2] for x in others):
        collision = True
        print(f"\n  C1 CONFIRMED: path {p} is also owned by an ACTIVE workflow "
              f"{[(x[0], x[1]) for x in others if x[2]]}")
if not collision:
    print("\n  C1 NOT the cause: no other ACTIVE workflow claims WF-2's webhook path")

print("\n" + "=" * 96)
print("WF-2 TRIGGER SANITY (C2)")
print("=" * 96)
st, wf2 = api(f"/api/v1/workflows/{WF2}")
print(f"  active={wf2.get('active')}  versionId={wf2.get('versionId')}  "
      f"nodes={len(wf2.get('nodes') or [])}")
print(f"  updatedAt={wf2.get('updatedAt')}")
trigs = [n for n in (wf2.get("nodes") or [])
         if n["type"].endswith(".webhook") or "trigger" in n["type"].lower()]
for n in trigs:
    print(f"  trigger [{n['name']}] type={n['type']} disabled={n.get('disabled', False)}")
    print(f"      params={json.dumps(n.get('parameters') or {}, ensure_ascii=False)[:220]}")
    print(f"      credentials={list((n.get('credentials') or {}).keys())}")

cfg = {}
for n in (wf2.get("nodes") or []):
    if n["name"] == "CONFIG":
        try:
            cfg = json.loads((n.get("parameters") or {}).get("jsonOutput") or "{}")
        except Exception:
            cfg = {}
mode = cfg.get("WRITE_MODE")
print(f"\n  WRITE_MODE = {mode!r}")
if mode != "shadow":
    sys.exit(f"ABORT: WRITE_MODE is {mode!r}, refusing to activate anything but shadow")

print("\n" + "=" * 96)
print("ACTIVATE (and verify by re-reading, never by trusting the 200)")
print("=" * 96)
st, r = api(f"/api/v1/workflows/{WF2}/activate", "POST")
print(f"  POST activate -> {st}")
if isinstance(r, dict):
    print(f"  response active={r.get('active')} versionId={r.get('versionId')}")
else:
    print(f"  response: {str(r)[:300]}")

for attempt in range(1, 6):
    time.sleep(4)
    st, after = api(f"/api/v1/workflows/{WF2}")
    print(f"  re-read #{attempt}: active={after.get('active')}")
    if after.get("active"):
        break

print("\n" + "=" * 96)
print("WEBHOOK PROBE - the only proof that matters")
print("=" * 96)
hook = None
for n in (wf2.get("nodes") or []):
    if n["type"].endswith(".webhook"):
        hook = (n.get("parameters") or {}).get("path") or n.get("webhookId")
        break
if hook:
    url = f"{BASE}/webhook/{hook}"
    print(f"  POST {url}")
    req = urllib.request.Request(url, data=json.dumps({"__probe": "wf2-reactivate"}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as x:
            print(f"  -> {x.status} {x.read().decode('utf-8', 'replace')[:200]}")
            print("  WF-2 IS REACHABLE - replays will land")
    except urllib.error.HTTPError as e:
        print(f"  -> {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        print("  STILL UNREACHABLE - do not proceed to the recovery cycle")
