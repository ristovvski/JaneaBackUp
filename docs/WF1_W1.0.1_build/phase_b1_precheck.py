"""Phase B1 pre-checks, read-only. GREEN/RED per item, no writes.

  - WF-2 active + webhook 200 (probe carries a harmless __preflight_probe marker so it's
    identifiable in logs, not a real event)
  - a clean WF-2S cycle at the new cap=20 (deployed moments ago in A1)
  - WF-ERR alive
  - mario@janeasystems.com present in WF-2's forward map
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
WF2S = "6Y92ryBwYoy6z0Jx"
GREEN, RED = [], []


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"X-N8N-API-KEY": KEY,
                                        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(r, timeout=180) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def find_wf(frag):
    st, d = n8n("/api/v1/workflows?limit=250")
    for w in (d.get("data") or []):
        if frag.lower() in str(w.get("name", "")).lower():
            return w
    return None


print("=" * 92)
print("WF-2 ACTIVE + WEBHOOK PROBE")
print("=" * 92)
st, wf2 = n8n(f"/api/v1/workflows/{WF2}")
print(f"  active={wf2.get('active')} versionId={wf2.get('versionId')}")
(GREEN if wf2.get("active") else RED).append(f"WF-2 active={wf2.get('active')}")
hook = None
for n in wf2.get("nodes") or []:
    if n["type"].endswith(".webhook"):
        hook = (n.get("parameters") or {}).get("path") or n.get("webhookId")
if hook:
    url = f"{BASE}/webhook/{hook}"
    req = urllib.request.Request(url, data=json.dumps({"__preflight_probe": "b1"}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as x:
            print(f"  webhook probe -> {x.status}")
            GREEN.append("WF-2 webhook probe 200")
    except urllib.error.HTTPError as e:
        print(f"  webhook probe -> {e.code}")
        RED.append(f"WF-2 webhook probe {e.code}")

print("\n" + "=" * 92)
print("WF-2S: CLEAN CYCLE AT NEW CAP=20")
print("=" * 92)
st, ex = n8n(f"/api/v1/executions?workflowId={WF2S}&limit=10")
rows = sorted([r for r in (ex.get("data") or []) if r.get("startedAt")],
              key=lambda r: r["startedAt"], reverse=True)
newest = rows[0] if rows else None
if newest:
    print(f"  newest execution: {newest['startedAt']} status={newest.get('status')}")
    age_min = (datetime.now(timezone.utc)
               - datetime.fromisoformat(newest["startedAt"].replace("Z", "+00:00"))
               ).total_seconds() / 60
    print(f"  age: {age_min:.1f} min")
    if age_min > 16:
        print("  no cycle yet since the cap=20 deploy - waiting for the next scheduled run...")
        deadline = time.time() + 16 * 60
        while time.time() < deadline:
            time.sleep(30)
            st, ex2 = n8n(f"/api/v1/executions?workflowId={WF2S}&limit=5")
            r2 = sorted([r for r in (ex2.get("data") or []) if r.get("startedAt")],
                       key=lambda r: r["startedAt"], reverse=True)
            if r2 and r2[0]["id"] != newest["id"] and r2[0].get("stoppedAt"):
                newest = r2[0]
                print(f"  new cycle landed: {newest['startedAt']} status={newest.get('status')}")
                break
    d = n8n(f"/api/v1/executions/{newest['id']}?includeData=true")
    if isinstance(d, tuple):
        _, d = d
    rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
    print(f"  status={newest.get('status')}  nodes_ran={list(rd.keys())}")
    if "Summary" in rd:
        try:
            j = rd["Summary"][0]["data"]["main"][0][0]["json"]
            print(f"  Summary: {json.dumps(j, ensure_ascii=False)[:400]}")
            batch = int(j.get("__batch") or 0)
            (GREEN if newest.get("status") == "success" and batch <= 20 else RED).append(
                f"WF-2S clean cycle at cap=20 (batch={batch}, status={newest.get('status')})")
        except Exception as e:
            RED.append(f"WF-2S Summary unreadable: {e}")
    elif newest.get("status") == "success":
        GREEN.append("WF-2S idle cycle, clean (no new sends to replay)")
    else:
        RED.append(f"WF-2S cycle status={newest.get('status')}, not clean")
else:
    RED.append("WF-2S has no retained executions at all")

print("\n" + "=" * 92)
print("WF-ERR ALIVE")
print("=" * 92)
wferr = find_wf("WF-ERR") or find_wf("error")
if wferr:
    st, w = n8n(f"/api/v1/workflows/{wferr['id']}")
    print(f"  {w.get('name')}  id={wferr['id']} active={w.get('active')}")
    st, ex = n8n(f"/api/v1/executions?workflowId={wferr['id']}&limit=5")
    rows = [r for r in (ex.get("data") or []) if r.get("startedAt")]
    print(f"  retained executions: {len(rows)}")
    (GREEN if w.get("active") else RED).append(f"WF-ERR active={w.get('active')}")
else:
    RED.append("WF-ERR workflow not found by name")

print("\n" + "=" * 92)
print("mario@janeasystems.com IN WF-2's FORWARD MAP")
print("=" * 92)
N = {n["name"]: n for n in wf2["nodes"]}
found_mario = False
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "mario@janeasystems.com" in blob:
        found_mario = True
        print(f"  found in node [{n['name']}]")
if "CONFIG" in N:
    cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
    blob = json.dumps(cfg, ensure_ascii=False)
    if "mario@janeasystems.com" in blob:
        found_mario = True
        print("  found in CONFIG")
(GREEN if found_mario else RED).append(f"mario@janeasystems.com present in WF-2 forward map: {found_mario}")

print("\n" + "=" * 92)
print("B1 VERDICT")
print("=" * 92)
for g in GREEN:
    print(f"  GREEN  {g}")
for r in RED:
    print(f"  RED    {r}")
print(f"\n  {len(GREEN)} green / {len(RED)} red")
