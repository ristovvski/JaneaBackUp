#!/usr/bin/env python3
"""Fire the tombstone hard-delete against the full 7,450-id list, chunked (never one bulk op --
the established OOM-shape lesson this project has been burned by once already). The 5 ids already
deleted in the isolated test run are skipped here (they'd just come back skipped_not_tombstoned
anyway since they no longer exist, but no reason to re-send them)."""
import json, os, ssl, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

CHUNK_SIZE = 500
ALREADY_DELETED_IN_TEST = {8856, 8857, 8859, 8860, 8861}


def fire(ids, dry_run):
    body = {"ids": ids, "dry_run": dry_run}
    req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/dnc-tombstone-hard-delete",
                                  method="POST", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        return json.loads(r.read())


def main():
    live = "--live" in sys.argv
    with open(os.path.join(HERE, "delete_target_ids.json"), encoding="utf-8") as f:
        ids = [i for i in json.load(f) if i not in ALREADY_DELETED_IN_TEST]
    print(f"total ids to process: {len(ids)} (5 already deleted in isolated test, excluded)")

    total_processed = total_skipped = 0
    for i in range(0, len(ids), CHUNK_SIZE):
        chunk = ids[i:i + CHUNK_SIZE]
        result = fire(chunk, dry_run=not live)
        total_processed += result["processed"]
        total_skipped += result["skipped_not_tombstoned"]
        print(f"chunk {i}-{i+len(chunk)}: {result}")
        if result["skipped_not_tombstoned"] > 0:
            print(f"  SKIPPED (no longer tombstoned, live state changed): {result['skipped_ids']}")
        time.sleep(1)

    print(f"\nTOTAL PROCESSED: {total_processed} (expected {len(ids)})")
    print(f"TOTAL SKIPPED (not tombstoned anymore): {total_skipped}")
    print("dry_run" if not live else "LIVE — rows deleted")


if __name__ == "__main__":
    main()
