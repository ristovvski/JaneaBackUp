#!/usr/bin/env python3
"""ITEM 1, corrected. The first run measured two things it could not measure.

Contamination 1 - the alert-claim half is worthless tonight: I rebuilt `__alerted_v1` from 50 to 0
at 11:24Z today, so nearly every historical claim is absent BY MY HAND. Only executions after that
reset can say anything, and there has been exactly one alert since.

Contamination 2 - the dedupe half returned n=0 because I guessed the field name. WF-1's `seen` store
was NOT touched today, so it is the honest signal - once read with the right key.

Also settles the watcher's "16 NEW errored executions": those ids are days old with
startedAt=None, and my filter did `(ts(x) or START) >= START`, so a missing timestamp defaults to
now and passes. A null that defaults into the accept branch - the same shape as this morning's bugs.
"""
import json, os, ssl, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1, WF2 = "2jdjKM2NJr473GdA", "jp7rum9Z0YDJkQWv"
RESET_AT = datetime.fromisoformat("2026-08-11T11:24:00+00:00")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:100]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print("A. settle the watcher's '16 new errors'")
p = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 60, "status": "error"})
rows = (p or {}).get("data") or []
nulls = [e for e in rows if not e.get("startedAt")]
dated = [e for e in rows if e.get("startedAt")]
print(f"   errored rows returned: {len(rows)}   with NO startedAt: {len(nulls)}")
print(f"   sample null-timestamp ids: {[e['id'] for e in nulls[:6]]}")
newest = sorted((ts(e['startedAt']) for e in dated), reverse=True)[:3]
print(f"   newest DATED error timestamps: {[t.isoformat() for t in newest]}")
since_fix = [t for t in (ts(e['startedAt']) for e in dated)
             if t and t > datetime.fromisoformat("2026-08-11T16:25:00+00:00")]
print(f"   genuinely new errors since the spacing fix (16:25Z): {len(since_fix)}")
print(f"   => the watcher's 16 were null-timestamp rows admitted by `or START`, NOT new failures"
      if not since_fix else "   => there ARE real new errors, investigate")

print("\nB. WF-1 Dedupe - the real key field")
wf = n8n(f"/api/v1/workflows/{WF1}")
ded = next((n for n in wf["nodes"] if n["name"] == "Dedupe"), None)
js = ((ded or {}).get("parameters") or {}).get("jsCode") or ""
for i, line in enumerate(js.splitlines(), 1):
    if "seen" in line or "key" in line or "return" in line:
        print(f"   {i:3}| {line.strip()[:114]}")
sd = (wf.get("staticData") or {}).get("global") or {}
seen = sd.get("seen") or {}
print(f"\n   seen store: {len(seen)} entries; sample keys {list(seen)[:3]}")

print("\nC. overlap exposure (this part WAS valid and stands)")
ids, cursor = [], None
while True:
    q = {"workflowId": WF1, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    pg = n8n("/api/v1/executions", q)
    ids += (pg or {}).get("data") or []
    cursor = (pg or {}).get("nextCursor")
    if not cursor:
        break
runs = [{"id": e["id"], "a": ts(e.get("startedAt")), "b": ts(e.get("stoppedAt"))}
        for e in ids if ts(e.get("startedAt")) and ts(e.get("stoppedAt"))]
runs.sort(key=lambda r: r["a"])
for r in runs:
    r["ov"] = 0
for i, r in enumerate(runs):
    for s in runs[i + 1:]:
        if s["a"] >= r["b"]:
            break
        r["ov"] += 1
        s["ov"] += 1
ovl = [r for r in runs if r["ov"] > 0]
print(f"   executions: {len(runs)}   overlapping at least one other: {len(ovl)} "
      f"({100 * len(ovl) / max(1, len(runs)):.0f}%)")
post = [r for r in runs if r["a"] > RESET_AT]
print(f"   executions AFTER my registry reset (the only uncontaminated window): {len(post)}")
print(f"   of those, overlapping: {sum(1 for r in post if r['ov'] > 0)}")
print("\n   VERDICT: structural exposure is CONFIRMED (same architecture, demonstrable overlap).")
print("   The claim-LOSS RATE is NOT measurable tonight - the registry was reset by me today, so")
print("   absence proves nothing. Re-run after a day of normal traffic for a real rate.")
