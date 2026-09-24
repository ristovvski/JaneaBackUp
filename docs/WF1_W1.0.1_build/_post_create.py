import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
wf=n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv"); C=wf.get("connections") or {}; N={n["name"]:n for n in wf["nodes"]}
for nm in ("Lead Create","Gate Lead Create","Skip Lead Create","Person Create","Gate Person Create",
           "Merge Reply Ctx","Ops Warn No Lead","Lead From Create","IF Lead Exists"):
    if nm in C or nm in N:
        print(f"{nm:<22} -> {json.dumps((C.get(nm) or {}).get('main'),ensure_ascii=False)[:150]}")
print("\nMerge Reply Ctx OUTPUT fields (what the reply path carries):")
d=n8n("/api/v1/executions/35038?includeData=true")
rd=((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
try:
    j=rd["Merge Reply Ctx"][0]["data"]["main"][0][0]["json"]
    print(" ", json.dumps({k:v for k,v in j.items() if k.startswith("__")},ensure_ascii=False)[:400])
except Exception as e: print("  n/a",e)
print("\nnode positions (for placing new ones):")
for nm in ("Merge Reply Ctx","IF No Lead","First Reply Gate","Ops Warn No Lead"):
    if nm in N: print(f"  {nm:<20} {N[nm].get('position')}")
print("\ncredentials used by Lead Create / Person Create:")
for nm in ("Lead Create","Person Create"):
    print(f"  {nm}: {json.dumps(N[nm].get('credentials'),ensure_ascii=False)}")
    print(f"     url={json.dumps(N[nm]['parameters'].get('url'),ensure_ascii=False)[:110]}")
    print(f"     keys={sorted(N[nm]['parameters'].keys())}")
