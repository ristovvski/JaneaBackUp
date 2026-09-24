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
wf=n8n("/api/v1/workflows/2jdjKM2NJr473GdA"); N={n["name"]:n for n in wf["nodes"]}
js=N["M7 Alert Gate"]["parameters"]["jsCode"]
print(f"=== M7 Alert Gate ({len(js.splitlines())} lines) ===")
for i,l in enumerate(js.splitlines(),1): print(f"{i:>3}| {l.rstrip()[:114]}")
C=wf.get("connections") or {}
print("\nM7 Alert Gate ->",json.dumps((C.get("M7 Alert Gate") or {}).get("main"),ensure_ascii=False)[:200])
print("M7 IF Should Alert ->",json.dumps((C.get("M7 IF Should Alert") or {}).get("main"),ensure_ascii=False)[:220])
print("\n=== M7 IF Should Alert condition ===")
print(json.dumps(N["M7 IF Should Alert"]["parameters"],ensure_ascii=False)[:600])
