import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
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
d=n8n("/api/v1/executions/24862?includeData=true")
rd=((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
nz=rd["Normalize"][0]["data"]["main"][0][0]["json"]
msgs=nz.get("msgs") or nz.get("recent_messages") or []
print(f"exec 24862 Normalize msgs: {len(msgs)}")
for m in msgs: print(f"   {m.get('creation_time')}  is_reply={m.get('is_reply')}  {str(m.get('message'))[:80]!r}")
raw=rd["Webhook"][0]["data"]["main"][0][0]["json"]; raw=raw.get("body",raw)
rm=raw.get("recent_messages") or []
print(f"\nraw webhook recent_messages: {len(rm)}")
for m in rm: print(f"   {m.get('creation_time')}  is_reply={m.get('is_reply')}  {str(m.get('message'))[:80]!r}")
a=(pd("/api/v2/activities/44174") or {}).get("data") or {}
note=str(a.get("note") or "")
print(f"\nactivity 44174 note ({len(note)} chars):")
print(note[:600])
print("\nother WF-1 execs for this lead on Aug 16:")
