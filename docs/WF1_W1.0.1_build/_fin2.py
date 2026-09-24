import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
PDT=os.environ["PIPEDRIVE_API_TOKEN"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
d=n8n("/api/v1/executions/35110?includeData=true")
rd=((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
def o(nm):
    try: return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception: return None
print("=== exec 35110 (Lara SENT) creation path ===")
for nm in ("Body Person Create","Person Create","Body Lead Create","Gate Lead Create","Lead Create","Skip Lead Create"):
    j=o(nm)
    if j is None: print(f"  {nm:<22} did not run"); continue
    if nm=="Body Lead Create":
        print(f"  {nm:<22} __skip={j.get('__skip')} reason={j.get('__block_reason')!r}")
        print(f"       title={(j.get('__body') or {}).get('title')!r} person_id={(j.get('__body') or {}).get('person_id')}")
    elif nm in ("Lead Create","Person Create"):
        dd=j.get("data") or j
        print(f"  {nm:<22} success={j.get('success')} id={(dd or {}).get('id')}")
    else:
        print(f"  {nm:<22} {json.dumps({k:v for k,v in list(j.items())[:4]},ensure_ascii=False)[:100]}")
err=((d.get("data") or {}).get("resultData") or {}).get("error") or {}
if err: print(f"  ERROR: {str(err.get('message'))[:120]}")
print("\n=== Lara in Pipedrive now ===")
s=pd("/api/v2/persons/search?fields=email&exact_match=true&limit=5&term=lara.lyberg%40citizensbank.com")
items=((s or {}).get("data") or {}).get("items") or []
for it in items:
    pid=(it.get("item") or {}).get("id")
    p=(pd(f"/api/v2/persons/{pid}") or {}).get("data") or {}
    L=(pd(f"/v1/leads?limit=50&person_id={pid}&archived_status=all") or {}).get("data") or []
    print(f"  person {pid} name={p.get('name')!r} add={p.get('add_time')} leads={len(L)}")
    for l in L: print(f"     {l.get('id')} {str(l.get('title'))[:56]!r} archived={l.get('is_archived')}")
