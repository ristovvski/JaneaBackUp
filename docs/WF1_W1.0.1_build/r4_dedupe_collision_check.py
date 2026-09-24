#!/usr/bin/env python3
"""CRITICAL pre-flip check. Nik's reply reached WF-2 TWICE:
  08:11:55Z  genuine Smartlead webhook (UA axios/0.19.2)
  08:45:07Z  WF-2R reconciler replay   (UA axios/1.18.0)

WF-2's Dedupe key is  event|campaign_id|sl_lead_id|timestamp.  If the two paths disagree on ANY
component - and `timestamp` is the obvious candidate, since Smartlead's webhook field and
leads-statistics' history time need not be byte-identical - then the replay is NOT seen as a
duplicate, and in live mode the reply would be processed twice: two forwards, two activities.

That is the same double-forward class already blocking the flip on Make's side. Read-only.
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
EMAIL = "pii-c61c7d08@example.invalid"
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    r = urllib.request.Request(f"{BASE}{path}?{q}" if q else f"{BASE}{path}",
                               headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
        return json.load(x)


found = []
d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60})
for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
    if str(e.get("startedAt") or "") < "2026-08-07T08:00":
        continue
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})

    def g(nm, key):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"].get(key)
        except Exception:
            return None

    nz_email = str(g("Normalize", "lead") or "")
    try:
        lead_email = rd["Normalize"][0]["data"]["main"][0][0]["json"]["lead"]["email"]
    except Exception:
        lead_email = None
    if str(lead_email or "").lower() != EMAIL:
        continue
    try:
        hdrs = rd["Webhook"][0]["data"]["main"][0][0]["json"].get("headers") or {}
    except Exception:
        hdrs = {}
    found.append({
        "exec": e["id"], "startedAt": e.get("startedAt"), "status": e.get("status"),
        "ua": hdrs.get("user-agent"),
        "reconciled": g("Normalize", "__reconciled"),
        "reconciled_by": g("Normalize", "__reconciled_by"),
        "event": g("Normalize", "event"),
        "raw_event": g("Normalize", "raw_event"),
        "campaign_id": g("Normalize", "campaign_id"),
        "sl_lead_id": g("Normalize", "sl_lead_id"),
        "timestamp": g("Normalize", "timestamp"),
        "dedupe_key": g("Dedupe", "__dedupe_key"),
        "duplicate": g("Dedupe", "__duplicate"),
        "category": g("Classify Parse", "__category"),
        "forward_to": g("Forward Resolve", "__forward_to"),
        "write_mode": g("CONFIG", "WRITE_MODE"),
    })

print(f"WF-2 executions carrying {EMAIL}: {len(found)}\n")
for f in found:
    print(f"  exec {f['exec']}  {f['startedAt']}  UA={f['ua']}")
    print(f"      reconciled={f['reconciled']} by={f['reconciled_by']} "
          f"raw_event={f['raw_event']!r}")
    print(f"      campaign_id={f['campaign_id']!r} sl_lead_id={f['sl_lead_id']!r}")
    print(f"      timestamp={f['timestamp']!r}")
    print(f"      dedupe_key={f['dedupe_key']!r}  duplicate={f['duplicate']}")
    print(f"      category={f['category']!r} forward_to={f['forward_to']!r} "
          f"mode={f['write_mode']}")
    print()

print("=" * 96)
if len(found) < 2:
    print("only one execution found - no collision to assess")
else:
    keys = [f["dedupe_key"] for f in found]
    same = len(set(keys)) == 1
    dup_flagged = any(f["duplicate"] for f in found[1:])
    print(f"dedupe keys identical across the two paths: {same}")
    for i, k in enumerate(keys):
        print(f"   [{i}] {k!r}")
    print(f"second execution flagged duplicate: {dup_flagged}")
    print()
    if same and dup_flagged:
        print("VERDICT: SAFE - the reconciler replay collapses onto the genuine webhook. "
              "In live mode this reply would be processed exactly once.")
    else:
        print("VERDICT: *** DOUBLE-PROCESSING RISK ***")
        diffs = [k for k in ("event", "campaign_id", "sl_lead_id", "timestamp")
                 if len({str(f[k]) for f in found}) > 1]
        print(f"  dedupe key components that DISAGREE between the two paths: {diffs}")
        print("  In WRITE_MODE=live this reply would be forwarded and activity-logged TWICE.")
        print("  This is a FLIP BLOCKER for WF-2R + WF-2 running together.")

json.dump(found, open(os.path.join(HERE, "wf1-release-evidence",
                                   "r4_dedupe_collision.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False, default=str)
print("\nwrote wf1-release-evidence/r4_dedupe_collision.json")
