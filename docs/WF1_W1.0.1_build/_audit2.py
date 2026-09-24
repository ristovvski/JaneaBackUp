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
NAME={"C07LTD8UT70":"#lead-processing(TEAM)","C0B8GCVNR5W":"#niks-channel","C0BQM1X9ZUY":"#gtm-telemetry"}
WFS={"2jdjKM2NJr473GdA":"WF-1","jp7rum9Z0YDJkQWv":"WF-2","6Y92ryBwYoy6z0Jx":"WF-2S",
     "U8Bb7Pdq7S6nzYPa":"WF-2R","nK3yIOqRcBearV8s":"WF-2H","BbrXPABgOaaTJjD6":"WF-ERR"}
for wid,label in WFS.items():
    wf=n8n(f"/api/v1/workflows/{wid}"); N={n["name"]:n for n in wf["nodes"]}
    cfgnode=N.get("CONFIG") or {}
    raw=(cfgnode.get("parameters") or {}).get("jsonOutput") or json.dumps(cfgnode.get("parameters") or {})
    try: cfg=json.loads(raw)
    except Exception:
        cfg={}
        for k,v in re.findall(r'"(\w*channel\w*)":\s*"([A-Z0-9]{9,})"',raw): cfg[k]=v
    keys={k:v for k,v in cfg.items() if isinstance(v,str) and re.match(r'^C[A-Z0-9]{8,}$',v)}
    print(f"== {label}  channel keys: "+", ".join(f"{k}={NAME.get(v,v)}" for k,v in keys.items()))
    for n in wf["nodes"]:
        if not n["type"].endswith("slack"): continue
        blob=json.dumps(n.get("parameters") or {},ensure_ascii=False)
        m=re.search(r'json\.(\w*channel\w*)',blob)
        key=m.group(1) if m else None
        dest=NAME.get(keys.get(key,""),keys.get(key) or "UNRESOLVED")
        flag=""
        if dest.endswith("(TEAM)"):
            if any(w in n["name"].lower() for w in ("warn","stale","suppress","error","digest","report","secret")):
                flag="  <-- META-TRAFFIC IN THE SIGNAL CHANNEL"
        print(f"   {n['name']:<28} key={str(key):<26} -> {dest}{flag}")
