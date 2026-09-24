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
wf=n8n("/api/v1/workflows/2jdjKM2NJr473GdA"); N={n["name"]:n for n in wf["nodes"]}; C=wf.get("connections") or {}
g=N["Lead Create Gate"]["parameters"]
for i,rule in enumerate(g.get("rules",{}).get("values",[])):
    conds=rule.get("conditions",{}).get("conditions",[])
    print(f"RULE {i}: outputKey={rule.get('outputKey')}")
    for c in conds: print(f"   {str(c.get('leftValue'))[:400]}")
print(f"\nfallback={g.get('options',{}).get('fallbackOutput')}")
print(f"\nLead Create Gate -> {json.dumps((C.get('Lead Create Gate') or {}).get('main'),ensure_ascii=False)[:220]}")
print(f"PID Resolved -> {json.dumps((C.get('PID Resolved') or {}).get('main'),ensure_ascii=False)[:160]}")
print(f"PID Resolved pos={N['PID Resolved']['position'] if 'PID Resolved' in N else '?'}  LeadSearch pos={N['Lead Search']['position']}")
print(f"Lead Search creds={json.dumps(N['Lead Search'].get('credentials'),ensure_ascii=False)}")
