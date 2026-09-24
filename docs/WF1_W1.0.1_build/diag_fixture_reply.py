#!/usr/bin/env python3
"""Why did the fixture reply resolve no lead, when the lead is demonstrably reachable?

Pulls, from the execution itself rather than from reasoning:
  * R Person Search / R Person Pick : __person_candidates, __person_id, __person_dupes
  * R Lead List                     : one output item PER CANDIDATE - so the item count IS the
                                      number of person_id requests, and each item's rows reveal
                                      which person was actually queried
  * Lead Resolve                    : __lead_candidates_read, __lead_read_errors, __lead_id,
                                      __no_lead, __leads_page_saturated, __person_id, adoption
  * First Reply Gate / Reply Alert  : did the alert fire, ok, and to WHICH channel
  * Dedupe + staticData             : what key state P0-1b left behind with lead=None

Then re-reads Pipedrive NOW for each candidate, so an index-lag theory is tested against the same
call the workflow made rather than assumed.
"""
import json, os, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"
EMAIL = "pii-c61c7d08@example.invalid"
LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
TEAM, OPS = "C07LTD8UT70", "C0B8GCVNR5W"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"  n8n read failed: {str(e)[:120]}")
        return None


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:110]}


def out_items(rd, nm):
    """ALL output items of a node - with pagination there is one per candidate person."""
    try:
        return [i["json"] for i in rd[nm][0]["data"]["main"][0]]
    except Exception:
        return []


def first(rd, nm, k, d=None):
    it = out_items(rd, nm)
    return it[0].get(k, d) if it else d


ex = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 40})
target = None
for e in sorted((ex or {}).get("data") or [], key=lambda r: str(r.get("startedAt")), reverse=True):
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    if not det:
        continue
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    lead = first(rd, "Normalize", "lead") or {}
    if str(lead.get("email", "")).lower() == EMAIL:
        target = (e, rd)
        break
if not target:
    sys.exit(f"no recent WF-2 execution for {EMAIL}")
e, rd = target
print(f"exec {e['id']}  {e.get('startedAt')}  status={e.get('status')}")
print(f"nodes that ran: {len(rd)}")

print("\n--- (b) did candidates populate at all? ---")
for nm in ("R Person Search", "R Person Pick", "R Person Verify Apply"):
    items = out_items(rd, nm)
    if not items:
        print(f"  {nm}: DID NOT RUN")
        continue
    j = items[0]
    print(f"  {nm}: person_id={j.get('__person_id')!r} found={j.get('__person_found')!r} "
          f"dupes={j.get('__person_dupes')!r}")
    print(f"      __person_candidates = {j.get('__person_candidates')!r}")

print("\n--- (a) which persons were ACTUALLY queried (one output item per request) ---")
pages = out_items(rd, "R Lead List")
print(f"  R Lead List emitted {len(pages)} item(s) => {len(pages)} person_id request(s)")
for i, p in enumerate(pages):
    rows = p.get("data") if isinstance(p.get("data"), list) else None
    if rows is None:
        print(f"    [{i}] NO .data (error item) keys={sorted(p.keys())[:8]}")
        continue
    pids = sorted({str(r.get('person_id')) for r in rows})
    print(f"    [{i}] rows={len(rows)} person_ids={pids} "
          f"has_fixture={any(str(r.get('id')) == LEAD for r in rows)}")
    for r in rows[:4]:
        print(f"         {str(r.get('id'))[:8]} archived={r.get('is_archived')} "
              f"{str(r.get('title'))[:52]!r}")

print("\n--- Lead Resolve verdict ---")
lr = out_items(rd, "Lead Resolve")
if lr:
    j = lr[0]
    for k in ("__lead_id", "__lead_how", "__no_lead", "__person_id", "__person_adopted",
              "__person_candidates", "__lead_pages", "__lead_rows", "__lead_candidates_read",
              "__lead_read_errors", "__leads_page_saturated"):
        print(f"  {k:<26} {j.get(k)!r}")
else:
    print("  Lead Resolve DID NOT RUN")

print("\n--- alert path (no-lead must NOT suppress it) ---")
g = out_items(rd, "First Reply Gate")
if g:
    print(f"  gate: should={g[0].get('__should_alert')!r} reason={g[0].get('__alert_reason')!r}")
ra = out_items(rd, "Reply Alert")
if not ra:
    print("  Reply Alert: DID NOT RUN")
else:
    j = ra[0]
    ts = (j.get("message") or {}).get("ts") or j.get("ts")
    ch = j.get("channel")
    where = "TEAM #lead-processing" if ch == TEAM else ("OPS" if ch == OPS else str(ch))
    print(f"  Reply Alert: ok={j.get('ok')!r} channel={ch} ({where}) ts={ts} "
          f"err={j.get('error')!r}")
    if j.get("ok") is True and ts:
        print(f"  PERMALINK: https://janea.slack.com/archives/{ch}/p{str(ts).replace('.', '')}")
for w in ("Ops Warn No Lead", "Ops Warn Classify", "Ops Warn Unknown Inbox"):
    if w in rd:
        jj = out_items(rd, w)
        print(f"  {w}: ran, ok={(jj[0].get('ok') if jj else None)!r} "
              f"channel={(jj[0].get('channel') if jj else None)}")

print("\n--- (P0-1b) claim state with lead=None ---")
dk = first(rd, "Dedupe", "__dedupe_key")
dup = first(rd, "Dedupe", "__duplicate")
print(f"  __dedupe_key={dk!r} __duplicate={dup!r}")
wf = n8n(f"/api/v1/workflows/{WF2}")
seen = ((wf or {}).get("staticData") or {}).get("global", {}).get("wf2_seen") or {}
print(f"  wf2_seen entries={len(seen)}   this key claimed={dk in seen if dk else 'n/a'}")
print("  (claimed=False on a no-lead run is CORRECT: the event stays replayable)")
claims = [n for n in ("Claim SENT", "Claim Bounce", "Claim Unsub", "Claim Nurture",
                      "Reply CRM Done", "NoOp Lead Exists") if n in rd]
print(f"  claim nodes that ran: {claims or 'none'}")

print("\n--- (c) index lag: re-read Pipedrive NOW, same calls ---")
cands = (first(rd, "R Person Pick", "__person_candidates") or [])
print(f"  candidates from the execution: {cands}")
for c in (cands or [85506]):
    rows = (pd(f"/v1/leads?limit=100&person_id={c}") or {}).get("data") or []
    print(f"    person {c}: {len(rows)} lead(s) now, has_fixture="
          f"{any(str(r.get('id')) == LEAD for r in rows)}")
srch = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=20&"
          f"term={urllib.parse.quote(EMAIL)}")
items = ((srch or {}).get("data") or {}).get("items") or []
print(f"  persons/search NOW returns {len(items)} item(s): "
      f"{[ (i.get('item') or {}).get('id') for i in items ]}")
