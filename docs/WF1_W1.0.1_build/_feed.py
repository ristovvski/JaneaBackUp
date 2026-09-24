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
tgt={"R Lead List","Body Reply Activity","Merge Reply Ctx","Body Lead Create","IF R Person Resolved"}
for src,v in C.items():
    for gi,grp in enumerate(v.get("main") or []):
        for c in (grp or []):
            if c.get("node") in tgt: print(f"  {src}  --out{gi}-->  {c.get('node')}")
print()
for nm in ("R Lead List","Merge Reply Ctx"):
    n=N.get(nm); print(f"--- {nm} ({n['type'].split('.')[-1]}) pos={n.get('position')}")
    print("    "+json.dumps(n.get("parameters"),ensure_ascii=False)[:420])
    print(f"    -> {json.dumps((C.get(nm) or {}).get('main'),ensure_ascii=False)[:150]}")
print("\n--- Body Reply Activity lead_id/deal lines")
js=N["Body Reply Activity"]["parameters"]["jsCode"]
for i,l in enumerate(js.splitlines(),1):
    if "lead_id" in l or "deal" in l.lower(): print(f"  {i:>3}| {l.rstrip()[:110]}")
