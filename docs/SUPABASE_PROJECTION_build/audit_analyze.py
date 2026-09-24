#!/usr/bin/env python3
"""Local, read-only analysis of the audit_out/ dumps. No network calls."""
import json
import os
import random
from datetime import datetime, timezone
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audit_out")

def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)

registry = load("n8n_registry.json")
domains = load("n8n_domains.json")
claims = load("n8n_claims.json")
sb_registry = load("supabase_registry.json")
sb_domains = load("supabase_domains.json")
sb_meta = load("supabase_meta.json")

CUTOFF = datetime(2026, 9, 1, tzinfo=timezone.utc)

def parse_ts(v):
    if not v:
        return None
    v2 = v.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(v2)
    except Exception:
        return None

def norm_ts(v):
    d = parse_ts(v)
    return d.isoformat() if d else None

# --- 1. registry rows since 1 Sep, grouped by reason ---
since = [r for r in registry if (parse_ts(r.get("added_at")) or parse_ts(r.get("createdAt")) or CUTOFF) >= CUTOFF]
by_reason = defaultdict(list)
for r in since:
    by_reason[r.get("reason") or "(null)"].append(r)

print(f"=== REGISTRY ROWS SINCE 2026-09-01 ===  total={len(since)} (of {len(registry)} all-time)")
for reason, rows in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
    print(f"  {reason:30s} {len(rows)}")

def dump_rows(rows, fname, fields=("identity_key","full_name","email_lc","linkedin_url_norm",
                                    "reason","entry_type","source","source_ref","pipedrive_person_id",
                                    "status","added_at","owner_tag","reply_category","source_signal")):
    with open(os.path.join(OUT, fname), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in fields}, ensure_ascii=False) + "\n")

for reason in ["reply_dnc", "meeting_dnc", "sales_personal_outreach", "unsubscribe", "client",
               "event_contacted", "manual_sheet", "manual_offboard_eligible", "offboard", "(null)"]:
    rows = by_reason.get(reason, [])
    dump_rows(rows, f"since_sep1_{reason}.jsonl")
    print(f"  -> wrote since_sep1_{reason}.jsonl ({len(rows)} rows)")

# --- 2. active count consistency n8n vs supabase ---
n8n_active = [r for r in registry if r.get("status") == "active"]
sb_active = [r for r in sb_registry if r.get("status") == "active"]
print(f"\n=== ACTIVE COUNT CONSISTENCY ===")
print(f"  n8n active:      {len(n8n_active)}")
print(f"  supabase active: {len(sb_active)}")
print(f"  MATCH" if len(n8n_active) == len(sb_active) else "  MISMATCH")
print(f"  n8n total: {len(registry)}  supabase total: {len(sb_registry)}")

# --- 3. 100-row field-by-field sample ---
REGISTRY_COLUMNS = [
    "id", "identity_key", "norm_v", "linkedin_url_norm", "email_lc", "full_name",
    "pipedrive_person_id", "entry_type", "reason", "source", "source_ref", "source_signal",
    "correlation_id", "date_precision", "expiry_review_pending", "offboard_removable",
    "also_flagged", "projections_state", "owner_tag", "status", "added_at", "removed_at",
    "removed_reason", "reply_category", "expires_at", "createdAt", "updatedAt",
]
TS_COLUMNS = {"added_at", "removed_at", "expires_at", "createdAt", "updatedAt"}
random.seed(20260915)
sample = random.sample(registry, min(100, len(registry)))
sb_by_id = {r["id"]: r for r in sb_registry}
mismatches = []
missing = []
for n_row in sample:
    s_row = sb_by_id.get(n_row["id"])
    if not s_row:
        missing.append(n_row["id"])
        continue
    for col in REGISTRY_COLUMNS:
        nv, sv = n_row.get(col), s_row.get(col)
        if col in TS_COLUMNS:
            nv, sv = norm_ts(nv), norm_ts(sv)
        if nv != sv:
            mismatches.append((n_row["id"], col, nv, sv))
print(f"\n=== 100-ROW FIELD-BY-FIELD SAMPLE ===")
print(f"  sampled=100 missing_in_supabase={len(missing)} field_mismatches={len(mismatches)}")
for m in mismatches[:30]:
    print("   ", m)
if missing:
    print("   missing ids:", missing[:20])

# --- 4. domains: sample 20 + full compare ---
n8n_dom_by_key = {r["domain"]: r for r in domains}
sb_dom_by_key = {r["domain"]: r for r in sb_domains}
dom_missing = [d for d in n8n_dom_by_key if d not in sb_dom_by_key]
dom_extra = [d for d in sb_dom_by_key if d not in n8n_dom_by_key]
random.seed(20260915)
dom_sample = random.sample(list(n8n_dom_by_key.keys()), min(20, len(n8n_dom_by_key)))
print(f"\n=== DOMAINS: n8n={len(n8n_dom_by_key)} supabase={len(sb_dom_by_key)} missing_from_sb={len(dom_missing)} extra_in_sb={len(dom_extra)} ===")
print("  20-domain sample presence check:")
for d in dom_sample:
    in_sb = "OK" if d in sb_dom_by_key else "MISSING"
    print(f"    {d:35s} n8n=OK supabase={in_sb}")

# --- 5. claims queue depth ---
print(f"\n=== CLAIMS QUEUE (current) ===  rows={len(claims)}")
for c in claims:
    print("   ", {k: c.get(k) for k in ("claim_key","family","workflow","event_time","claimed_at")})

# --- 6. reconcile meta rows ---
print(f"\n=== SUPABASE dnc_registry_meta (last 20 by last_sync_at desc) ===")
for m in sb_meta:
    print("   ", {k: m.get(k) for k in ("source","row_count","last_sync_at")})

# --- 7. reverse-check candidates: registry rows since 1 Sep worth scrutiny ---
# event_contacted = weakest signal ("we touched them", not that they engaged) -- worth listing
# reason=(null) or entry_type=manual with thin source_ref -- worth listing
print(f"\n=== REVERSE-CHECK CANDIDATE COUNTS (since 2026-09-01) ===")
for reason in ["event_contacted", "manual_sheet", "(null)"]:
    print(f"  reason={reason}: {len(by_reason.get(reason, []))}  (see since_sep1_{reason}.jsonl)")

print("\nDONE")
