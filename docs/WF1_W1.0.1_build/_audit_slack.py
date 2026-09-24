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
TEAM="C07LTD8UT70"; NIK="C0B8GCVNR5W"; TEL="C0BQM1X9ZUY"
WFS={"2jdjKM2NJr473GdA":"WF-1","jp7rum9Z0YDJkQWv":"WF-2","6Y92ryBwYoy6z0Jx":"WF-2S",
     "U8Bb7Pdq7S6nzYPa":"WF-2R","nK3yIOqRcBearV8s":"WF-2H","BbrXPABgOaaTJjD6":"WF-ERR"}
print("Slack nodes that target the TEAM channel (must be clean live lead alerts only):\n")
for wid,label in WFS.items():
    wf=n8n(f"/api/v1/workflows/{wid}")
    for n in wf["nodes"]:
        if not n["type"].endswith("slack"): continue
        blob=json.dumps(n.get("parameters") or {},ensure_ascii=False)
        chan=None
        if TEAM in blob: chan="TEAM"
        elif NIK in blob: chan="niks"
        elif TEL in blob: chan="telemetry"
        else:
            m=re.search(r'slack_channel_\w+|ops_channel|team_channel',blob)
            chan=("via CONFIG:"+m.group(0)) if m else "?"
        if chan=="TEAM":
            warnish=any(k in n["name"].lower() for k in ("warn","error","alert suppressed","stale","digest","report"))
            print(f"  {label:<6} {n['name']:<28} -> TEAM   {'<-- REVIEW: name reads like meta-traffic' if warnish else ''}")
print("\nSlack nodes by resolved destination (counts):")
for wid,label in WFS.items():
    wf=n8n(f"/api/v1/workflows/{wid}")
    c={"TEAM":0,"niks":0,"telemetry":0,"config-key":0,"?":0}
    for n in wf["nodes"]:
        if not n["type"].endswith("slack"): continue
        blob=json.dumps(n.get("parameters") or {},ensure_ascii=False)
        if TEAM in blob: c["TEAM"]+=1
        elif NIK in blob: c["niks"]+=1
        elif TEL in blob: c["telemetry"]+=1
        elif re.search(r'slack_channel_\w+|ops_channel|team_channel',blob): c["config-key"]+=1
        else: c["?"]+=1
    print(f"  {label:<6} {c}")
