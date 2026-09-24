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
wf=n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
N={n["name"]:n for n in wf["nodes"]}
js=N["Normalize"]["parameters"]["jsCode"].splitlines()
for i in range(28,60): print(f"{i+1:>3}| {js[i].rstrip()[:118]}")
cfg=json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
print("\nCONFIG.event_marker_canon =", json.dumps(cfg.get("event_marker_canon"),ensure_ascii=False))
