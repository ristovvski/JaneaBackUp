#!/usr/bin/env python3
"""Fire the Company DNC domains import (dnc_domains_import driver) against the prepared,
deduped/cleaned/free-mail-checked payload. Chunked, dry_run by default -- pass --live to write."""
import json, os, ssl, sys, urllib.request

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


def fire(rows, dry_run):
    body = {"rows": rows, "dry_run": dry_run}
    req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/dnc-domains-import",
                                  method="POST", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        return json.loads(r.read())


def main():
    live = "--live" in sys.argv
    with open(os.path.join(HERE, "domains_import_payload.json"), encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    print(f"total domains to process: {len(rows)}")

    total_processed = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        result = fire(chunk, dry_run=not live)
        total_processed += result["processed"]
        print(f"chunk {i}-{i+len(chunk)}: {result}")

    print(f"\nTOTAL PROCESSED: {total_processed} (expected {len(rows)})")
    print("dry_run" if not live else "LIVE — domains written")


if __name__ == "__main__":
    main()
