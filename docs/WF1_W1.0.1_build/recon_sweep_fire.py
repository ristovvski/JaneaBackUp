#!/usr/bin/env python3
"""READ ONLY. Everything needed before the live window:
  1. `Combine Summaries` / `Send Guard` code, to add the DRY RUN prefix.
  2. `PD Label Union` code - assert it really unions rather than replaces, BEFORE it writes labels
     for the first time ever (cumulative labels are a standing rule; this node has never run live).
  3. The exact pending person ids from dev execution 48563 - all 580, not just the 250 chunk, so the
     baseline cannot be defeated by the live run selecting a different slice (the DNC reply capture
     deployed today adds pending rows, so the set can move between runs).
"""
import json
import os
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SWEEP = "8qVXtI2ez5o6a9hc"
EXEC = "48563"
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


wf = n8n("/api/v1/workflows/%s" % SWEEP)
N = {n["name"]: n for n in wf["nodes"]}
print("sweep version=%s nodes=%d active=%s" % (wf.get("versionId"), len(wf["nodes"]),
                                               wf.get("active")))
for nm in ("Combine Summaries", "Send Guard", "PD Label Union", "PD Aggregate", "PD Limit Chunk"):
    js = (N[nm].get("parameters") or {}).get("jsCode") or ""
    print("=" * 74)
    print("=== %s ===" % nm)
    print(js)

print("=" * 74)
print("=== PD Get Lead For Labels / PD Patch Lead Labels parameters ===")
for nm in ("PD Get Lead For Labels", "PD Patch Lead Labels", "PD Write DNC Field"):
    n = N.get(nm)
    if not n:
        continue
    p = n.get("parameters") or {}
    print("  --- %s (onError=%s retryOnFail=%s) ---" % (nm, n.get("onError"), n.get("retryOnFail")))
    print("   " + json.dumps({k: v for k, v in p.items() if k != "jsCode"},
                             ensure_ascii=False, indent=1)[:1400].replace("\n", "\n   "))

# ---- the pending ids from the dev run
full = n8n("/api/v1/executions/%s?includeData=true" % EXEC)
run = (((full or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}


def items(nm):
    try:
        return [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
    except Exception:
        return []


pending = items("PD Filter Pending")
chunk = items("PD Limit Chunk")
classify = items("PD Classify")
print("\n=== ids from the dev run ===")
print("  PD Filter Pending : %d" % len(pending))
print("  PD Limit Chunk    : %d" % len(chunk))
print("  PD Classify       : %d" % len(classify))
pend_ids = [r.get("pipedrive_person_id") for r in pending if r.get("pipedrive_person_id")]
chunk_ids = [r.get("pipedrive_person_id") for r in chunk if r.get("pipedrive_person_id")]
print("  distinct pending person ids: %d" % len(set(pend_ids)))
print("  distinct chunk   person ids: %d" % len(set(chunk_ids)))
print("  chunk is a prefix of pending: %s" % (pend_ids[:len(chunk_ids)] == chunk_ids))
with_lead = [r for r in classify if r.get("has_open_lead")]
print("  chunk with open lead: %d  without: %d" % (len(with_lead),
                                                   len(classify) - len(with_lead)))

out = os.path.join(HERE, "fire_target_ids_%s.json" % EXEC)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"pending_ids": pend_ids, "chunk_ids": chunk_ids,
               "chunk_rows": [{"person_id": r.get("pipedrive_person_id"),
                               "identity_key": r.get("identity_key"),
                               "has_open_lead": r.get("has_open_lead"),
                               "lead_id": r.get("lead_id")} for r in classify]}, f,
              ensure_ascii=False, indent=1)
print("\n-> %s" % os.path.basename(out))
