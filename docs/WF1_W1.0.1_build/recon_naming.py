#!/usr/bin/env python3
"""READ-ONLY recon: what does deployed code key event capture on, and who parses campaign NAMES?

Scans every workflow in the estate (not just the ones I expect) for: event-capture logic, hardcoded
campaign ids, and any code that reads a campaign name. Prints the matching source lines so the
answer is quoted from the deployed body rather than summarised.
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


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


cur, wfs = None, []
while True:
    q = {"limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/workflows?" + urllib.parse.urlencode(q)) or {}
    wfs += d.get("data") or []
    cur = d.get("nextCursor")
    if not cur:
        break
print(f"workflows in estate: {len(wfs)}\n")

SIGNALS = {
    "event_contacted": "event_contacted",
    "event marker / Events Visiting": "Events Visiting",
    "hardcoded AI4 email ids": "3686181",
    "hardcoded AI4 LinkedIn ids": "512995",
    "campaign_ids CONFIG list": "campaign_ids",
    "event_campaign CONFIG": "event_campaign",
}
found = {k: [] for k in SIGNALS}
bodies = {}
for w in wfs:
    full = n8n(f"/api/v1/workflows/{w['id']}")
    bodies[w["id"]] = full
    blob = json.dumps(full, ensure_ascii=False)
    for k, needle in SIGNALS.items():
        if needle in blob:
            found[k].append((w["id"], w["name"], full.get("active")))

for k, v in found.items():
    print(f"### {k}: {len(v)}")
    for wid, nm, act in v[:14]:
        print(f"    {wid}  {'ACTIVE' if act else 'inact '}  {nm[:62]}")
    print()

# quote the actual lines that read a campaign name or an event marker
print("=" * 78)
print("SOURCE LINES that read campaign names / event markers")
print("=" * 78)
LINE = re.compile(r"Events Visiting|event_trio|event_marker|campaign_name|campaign\.name|"
                  r"event_contacted|marker", re.I)
for wid, full in bodies.items():
    shown = 0
    for n in full.get("nodes", []):
        js = (n.get("parameters") or {}).get("jsCode") or ""
        params = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
        src = js if js else params
        for line in src.splitlines():
            if LINE.search(line) and len(line.strip()) > 12:
                if shown == 0:
                    print(f"\n--- {full.get('name')[:56]} ({wid}) "
                          f"{'ACTIVE' if full.get('active') else 'inactive'} ---")
                print(f"   [{n['name'][:26]}] {line.strip()[:118]}")
                shown += 1
                if shown >= 8:
                    break
        if shown >= 8:
            break
