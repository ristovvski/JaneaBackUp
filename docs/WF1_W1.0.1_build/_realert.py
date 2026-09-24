import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
PDT=os.environ["PIPEDRIVE_API_TOKEN"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
FRAG="f6bfaf70"
print("=== the lead ===")
# find full id via person? try direct prefix match through recent leads
hits=[]
ex=(n8n("/api/v1/executions?workflowId=jp7rum9Z0YDJkQWv&limit=150") or {}).get("data") or []
print(f"scanning {len(ex)} WF-2 executions for {FRAG}")
for e in ex:
    d=n8n(f"/api/v1/executions/{e['id']}?includeData=true")
    rd=((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
    if not rd: continue
    blob=json.dumps(rd)
    if FRAG not in blob: continue
    def o(nm):
        try: return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception: return None
    nz=o("Normalize") or {}; g=o("First Reply Gate") or {}; al=o("Reply Alert") or {}
    hits.append({"id":e["id"],"at":e.get("startedAt"),"status":e.get("status"),
        "event":nz.get("event"),"lead_email":(nz.get("lead") or {}).get("email"),
        "campaign":nz.get("campaign_name"),
        "reason":g.get("__alert_reason"),"should":g.get("__should_alert"),
        "key":g.get("__alert_key"),"regsize":g.get("__alert_registry_size"),
        "ok":al.get("ok"),"chan":al.get("channel"),"cls":nz.get("__reply_class")})
print(f"executions touching it: {len(hits)}\n")
for h in sorted(hits,key=lambda x:str(x["at"])):
    print(f"exec {h['id']} {h['at']} status={h['status']} event={h['event']!r}")
    print(f"   lead={h['lead_email']!r} campaign={str(h['campaign'])[:40]!r} class={h['cls']!r}")
    print(f"   gate: should_alert={h['should']} reason={h['reason']!r} registry_size={h['regsize']}")
    print(f"   alert: ok={h['ok']} channel={h['chan']}")
    print(f"   key={h['key']!r}\n")
