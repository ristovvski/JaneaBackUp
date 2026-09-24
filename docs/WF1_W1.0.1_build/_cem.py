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
wf=n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
for n in wf["nodes"]:
    js=(n.get("parameters") or {}).get("jsCode") or ""
    if "campaign_event_map" in js:
        print(f"--- {n['name']} ---")
        for i,l in enumerate(js.splitlines(),1):
            if "campaign_event_map" in l or "event_name" in l or "hypothesis" in l:
                print(f"  {i:>3}| {l.rstrip()[:118]}")
