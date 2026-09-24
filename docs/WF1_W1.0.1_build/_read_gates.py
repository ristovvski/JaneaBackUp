import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
for wid,label,gates in (("jp7rum9Z0YDJkQWv","WF-2",("Gate Lead Create","Lead Resolve","R Person Pick")),
                        ("2jdjKM2NJr473GdA","WF-1",("Lead Create Gate","Lead Search","Select Existing Lead"))):
    wf=n8n(f"/api/v1/workflows/{wid}"); N={n["name"]:n for n in wf["nodes"]}; C=wf.get("connections") or {}
    print(f"########## {label} versionId={wf.get('versionId')} nodes={len(wf['nodes'])}")
    # any existing deal lookup?
    deals=[n["name"] for n in wf["nodes"] if "deal" in n["name"].lower()
           or "deals" in json.dumps(n.get("parameters") or {}).lower()]
    print(f"  nodes referencing deals: {deals or 'NONE'}")
    for g in gates:
        n=N.get(g)
        if not n: print(f"  --- {g}: ABSENT"); continue
        print(f"  --- {g} ({n['type'].split('.')[-1]}) pos={n.get('position')}")
        js=(n.get("parameters") or {}).get("jsCode")
        if js:
            for i,l in enumerate(js.splitlines(),1):
                if i<=6 or "lead_id" in l or "__skip" in l or "return" in l: print(f"     {i:>3}| {l.rstrip()[:104]}")
        else:
            print("     "+json.dumps(n.get("parameters"),ensure_ascii=False)[:520])
        print(f"     -> {json.dumps((C.get(g) or {}).get('main'),ensure_ascii=False)[:170]}")
    # who feeds the gate
    for src,v in C.items():
        for grp in (v.get("main") or []):
            for c in (grp or []):
                if c.get("node") in gates: print(f"  feeds {c.get('node')}: {src}")
    print()
