#!/usr/bin/env python3
"""Can rows be written to the dataTable over REST, or must the migration run inside n8n?
Previously recorded as 404. Re-probe rather than trust the note - if REST works the migration is a
loop; if not it needs a throwaway workflow. READ ONLY (GETs only)."""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
TID = "euyostwJYfJefItC"

PATHS = [
    "/api/v1/data-tables",
    f"/api/v1/data-tables/{TID}",
    f"/api/v1/data-tables/{TID}/rows",
    "/api/v1/dataTables",
    f"/api/v1/dataTables/{TID}/rows",
    "/rest/data-tables",
    f"/rest/data-tables/{TID}/rows",
]
for p in PATHS:
    try:
        r = urllib.request.Request(BASE + p, headers={"X-N8N-API-KEY": KEY,
                                                      "accept": "application/json"})
        with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
            body = x.read()[:220].decode("utf-8", "replace")
        print(f"  {x.status}  {p}\n        {body}")
    except urllib.error.HTTPError as e:
        print(f"  {e.code}  {p}")
    except Exception as e:
        print(f"  ERR  {p}  {str(e)[:70]}")
