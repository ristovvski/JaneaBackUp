#!/usr/bin/env python3
"""FIRE the combined removal batch: 7,138 S4 (event_contacted) + 348 manual_sheet = 7,486 rows.
Nik's GO, 2026-08-26. Tombstone via dnc_s4_retirement_removal, dry_run:false, chunked at 500/call.
Verifies each chunk's response before proceeding to the next."""
import json, os, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
FIX = os.path.join(HERE, "fixtures")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WEBHOOK = BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}"
CHUNK_SIZE = 500

s4 = json.load(open(os.path.join(FIX, "s4_retirement_recon.json"), encoding="utf-8"))
ms = json.load(open(os.path.join(FIX, "manual_sheet_full_ids.json"), encoding="utf-8"))
all_ids = list(s4["pure_s4_ids"]) + list(ms["ids"])
print(f"total ids to remove: {len(all_ids)} (s4={len(s4['pure_s4_ids'])} + manual_sheet={len(ms['ids'])})")
assert len(all_ids) == len(set(all_ids)), "duplicate ids across the two sets!"

total_processed = 0
for i in range(0, len(all_ids), CHUNK_SIZE):
    chunk = all_ids[i:i + CHUNK_SIZE]
    payload = {"row_ids": chunk, "dry_run": False}
    req = urllib.request.Request(WEBHOOK, method="POST", data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        result = json.loads(r.read())
    print(f"chunk {i}-{i+len(chunk)}: {result}")
    assert result.get("dry_run") is False, f"chunk {i} did not run in write mode!"
    assert result.get("processed") == len(chunk), f"chunk {i} processed count mismatch"
    total_processed += result["processed"]
    time.sleep(0.5)

print(f"\nTOTAL PROCESSED: {total_processed} (expected {len(all_ids)})")
