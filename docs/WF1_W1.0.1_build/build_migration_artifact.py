#!/usr/bin/env python3
"""Build the migration artifact for #26 — the exact 53 keys, their timestamps and their form.
READ ONLY. Writes alert_registry_migration.json."""
import json, os, ssl, urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
sd = wf.get("staticData") or {}
if isinstance(sd, str):
    sd = json.loads(sd)
G = sd.get("global") or {}
reg = G.get("__alerted_v1") or {}
seen = G.get("seen") or {}
print(f"WF-1 versionId {wf.get('versionId')}")
print(f"  __alerted_v1 : {len(reg)} keys   <- migrating these")
print(f"  seen         : {len(seen)} keys   (already dual-written, not in scope)")

rows = []
for k, v in reg.items():
    form = "P" if k.startswith("P") else ("L" if k.startswith("L") else
                                          ("M" if k.startswith("M") else "?"))
    camp = k.rsplit("|", 1)[-1] if "|" in k else None
    rows.append({"claim_key": k, "claimed_at": v, "form": form, "campaign": camp,
                 "family": "wf1_alert", "workflow": "WF-1",
                 "evidence": "migrated:staticData __alerted_v1"})
rows.sort(key=lambda r: str(r["claimed_at"]))
print(f"\nby key form   : {dict(Counter(r['form'] for r in rows))}")
print(f"by campaign   : {dict(Counter(str(r['campaign']) for r in rows))}")
ts = [r["claimed_at"] for r in rows if r["claimed_at"]]
print(f"timestamps    : {min(ts)[:19]}  ..  {max(ts)[:19]}")
bad = [r for r in rows if not r["claimed_at"]]
print(f"keys with no timestamp: {len(bad)}")

print("\n--- 5 example rows ---")
for r in rows[:3] + rows[-2:]:
    print(f"  {r['claim_key']:<46} {str(r['claimed_at'])[:19]}  form={r['form']}")

json.dump({"rows": rows, "source_version": wf.get("versionId")},
          open(os.path.join(HERE, "alert_registry_migration.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print(f"\nartifact: alert_registry_migration.json  ({len(rows)} rows)")
