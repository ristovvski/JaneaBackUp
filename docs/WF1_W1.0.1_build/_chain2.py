import json,os,re,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
d=n8n("/api/v1/executions/35110?includeData=true")
rd=((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
def o(nm):
    try: return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception: return None
print("=== SL Fetch Lead output (does Smartlead give us the name here?) ===")
sf=o("SL Fetch Lead") or {}
print(json.dumps(sf,ensure_ascii=False)[:500])
print("\n=== Person Id Final / Carry Person Ctx (who owns the pid) ===")
for nm in ("Person Id Final","Carry Person Ctx","Person Pick","IF Have Person Id","IF Person Resolved"):
    j=o(nm)
    print(f"  {nm:<20} {json.dumps(j,ensure_ascii=False)[:150] if j is not None else 'did not run'}")
wf=n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv"); N={n["name"]:n for n in wf["nodes"]}
print("\n=== Apply Enrich: why first/last are null ===")
js=N["Apply Enrich"]["parameters"].get("jsCode","")
for i,l in enumerate(js.splitlines(),1):
    if re.search(r"first|last|full_name|SL Fetch|name",l): print(f"  {i:>3}| {l.rstrip()[:112]}")
print("\n=== Carry Person Ctx source ===")
js2=N.get("Carry Person Ctx",{}).get("parameters",{}).get("jsCode","")
for i,l in enumerate(js2.splitlines(),1): print(f"  {i:>3}| {l.rstrip()[:112]}")
