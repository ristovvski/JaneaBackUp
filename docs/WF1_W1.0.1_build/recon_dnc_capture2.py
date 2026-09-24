#!/usr/bin/env python3
"""Two premises to check before building:
  (a) "WF-2's unsubscribe branch already writes the ledger" - my first pass found IF DNC ->
      Body SL Unsubscribe -> SL Unsubscribe, which is SMARTLEAD's unsubscribe endpoint. Does WF-2
      call DNC__UpsertLedger__v1 anywhere at all?
  (b) UpsertLedger THROWS on reason 'reply_dnc' without reply_category. WF-1 is HeyReach - does it
      have a reply category to supply?
READ ONLY."""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LEDGER = "RolYGL3J2CNg6Yp3"


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


print("=== (a) WHO calls DNC__UpsertLedger__v1, estate-wide? ===")
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
callers = []
for w in wfs:
    full = n8n(f"/api/v1/workflows/{w['id']}")
    blob = json.dumps(full, ensure_ascii=False)
    if LEDGER in blob or "UpsertLedger" in blob:
        nodes = [n["name"] for n in full["nodes"]
                 if LEDGER in json.dumps(n.get("parameters") or {}, ensure_ascii=False)
                 or "UpsertLedger" in json.dumps(n.get("parameters") or {}, ensure_ascii=False)]
        callers.append((w["id"], w["name"], full.get("active"), nodes))
for wid, nm, act, nodes in callers:
    print(f"  {wid}  {'ACTIVE' if act else 'inact '}  {nm[:46]:<46} nodes={nodes}")
if not callers:
    print("  NOBODY calls it.")

print("\n=== is WF-2's DNC branch a LEDGER write or a Smartlead unsubscribe? ===")
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
N2 = {n["name"]: n for n in wf2["nodes"]}
for nm in ("SL Unsubscribe", "Gate SL Unsubscribe", "U Lead DNC Label", "Mark DNC", "U Mark DNC"):
    n = N2.get(nm)
    if not n:
        print(f"  {nm}: ABSENT")
        continue
    p = n.get("parameters") or {}
    print(f"  {nm:<22} type={n['type'].split('.')[-1]:<12} url={str(p.get('url'))[:70]}")
print(f"\n  WF-2 mentions RolYGL3J2CNg6Yp3: {LEDGER in json.dumps(wf2, ensure_ascii=False)}")
print(f"  WF-2 executeWorkflow nodes: "
      f"{[n['name'] for n in wf2['nodes'] if 'executeWorkflow' in n['type']]}")

print("\n=== (b) does WF-1 have a reply category to satisfy reply_dnc? ===")
wf1 = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
b1 = json.dumps(wf1, ensure_ascii=False)
for token in ("reply_category", "classif", "sentiment", "negative", "is_dnc", "unsubscrib"):
    print(f"  WF-1 contains {token!r}: {token in b1.lower()}")
nz = N1 = {n["name"]: n for n in wf1["nodes"]}["Normalize"]["parameters"]["jsCode"]
print(f"  Normalize emits reply_category: {'reply_category' in nz}")
print("\n  WF-2 classifier nodes (what WF-1 lacks):")
print(f"    {[n['name'] for n in wf2['nodes'] if 'lassif' in n['name']]}")

print("\n=== the ledger's reason -> entry_type map (what reasons are legal) ===")
lg = n8n(f"/api/v1/workflows/{LEDGER}")
for n in lg["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    m = re.search(r"REASON_TO_ENTRY_TYPE\s*=\s*\{[^}]*\}", js, re.S)
    if m:
        print("  " + m.group(0)[:600].replace("\n", "\n  "))
        break
