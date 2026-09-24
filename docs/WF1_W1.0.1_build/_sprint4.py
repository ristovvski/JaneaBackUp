import json,os,ssl,urllib.parse,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
NEEDLE="pii-5a90b531@example.invalid"
cur=None; pages=0; hit=None
while pages<12 and not hit:
    q={"workflowId":"jp7rum9Z0YDJkQWv","limit":250}
    if cur: q["cursor"]=cur
    d=n8n("/api/v1/executions?"+urllib.parse.urlencode(q)) or {}
    rows=d.get("data") or []
    if not rows: break
    for r in rows:
        if not str(r.get("startedAt") or "").startswith("2026-08-11"): continue
        det=n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd=((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if NEEDLE not in json.dumps(rd): continue
        hit=(r,rd); break
    cur=d.get("nextCursor"); pages+=1
    if not cur: break
print(f"pages walked: {pages}")
if not hit:
    print("no WF-2 execution found for that lead on 2026-08-11 -> our write did NOT come from WF-2")
else:
    r,rd=hit
    print(f"exec {r['id']} {r.get('startedAt')} status={r.get('status')} nodes={len(rd)}")
    def o(nm):
        try: return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception: return None
    raw=o("Webhook") or {}; raw=raw.get("body",raw)
    print("\n  RAW WEBHOOK identity fields:")
    for k in ("event_type","to_email","to_name","sl_lead_email","campaign_id","campaign_name"):
        print(f"    {k:<16} {repr(raw.get(k))[:64]}")
    ld=raw.get("lead_data")
    print(f"    lead_data       {('ABSENT' if ld is None else json.dumps(ld)[:150])}")
    nz=o("Normalize") or {}
    L=nz.get("lead") or {}
    print(f"\n  NORMALIZE lead: full_name={L.get('full_name')!r} first={L.get('first')!r} last={L.get('last')!r}")
    print(f"                  email={L.get('email')!r} company={L.get('company')!r}")
    blc=o("Body Lead Create") or {}
    b=blc.get("__body") or {}
    print(f"\n  BODY LEAD CREATE title={b.get('title')!r}")
    bpc=o("Body Person Create") or {}
    pb=bpc.get("__body") or {}
    print(f"  BODY PERSON CREATE name={pb.get('name')!r}")
    print(f"\n  nodes that ran: {sorted(rd.keys())[:24]}")
