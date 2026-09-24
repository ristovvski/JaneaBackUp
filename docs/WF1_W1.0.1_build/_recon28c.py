import json,os,ssl,urllib.parse,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
HR=os.environ.get("HEYREACH_API_KEY"); CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
def hr(path,body):
    r=urllib.request.Request("https://api.heyreach.io/api/public"+path,method="POST",
        data=json.dumps(body).encode(),
        headers={"X-API-KEY":HR,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:150]}

# 1. ground truth: every OUTBOUND message in Alan's thread
conv=hr("/inbox/GetConversationsV2",{"filters":{},"offset":0,"limit":100})
alan=None
for c in (conv.get("items") or []):
    if "alan" in json.dumps(c.get("correspondentProfile") or {},ensure_ascii=False).lower(): alan=c;break
if not alan:
    for c in (conv.get("items") or []):
        if "Hi Alan," in json.dumps(c,ensure_ascii=False): alan=c;break
msgs=(alan or {}).get("messages") or []
out=[m for m in msgs if m.get("sender")=="ME"]
print(f"Alan thread: {len(msgs)} messages total, {len(out)} OUTBOUND (sender=ME)")
for m in out: print(f"   OUT {m.get('createdAt')}  {str(m.get('body'))[:70]!r}")

# 2. every WF-1 message_sent webhook for this lead
print("\nWF-1 message_sent webhooks naming Person-2f078c2e:")
cur=None; pages=0; found=[]
while pages<8:
    q={"workflowId":"2jdjKM2NJr473GdA","limit":250}
    if cur: q["cursor"]=cur
    d=n8n("/api/v1/executions?"+urllib.parse.urlencode(q)) or {}
    rows=d.get("data") or []
    if not rows: break
    for r in rows:
        det=n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd=((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        try:
            raw=rd["Webhook"][0]["data"]["main"][0][0]["json"]; raw=raw.get("body",raw)
        except Exception: continue
        if str(raw.get("event_type"))!="message_sent": continue
        ld=raw.get("lead") or {}
        if "alan" not in str(ld.get("full_name") or "").lower(): continue
        rm=raw.get("recent_messages") or []
        found.append((r.get("startedAt"),raw.get("timestamp"),[ (x.get("creation_time"),str(x.get("message"))[:50]) for x in rm ]))
    cur=d.get("nextCursor"); pages+=1
    if not cur: break
print(f"  found: {len(found)}")
for st,ts,rm in found:
    print(f"   exec@{st} payload_ts={ts}")
    for ct,msg in rm: print(f"       msg {ct}  {msg!r}")
print(f"\n  VERDICT: outbound in thread={len(out)}  vs message_sent webhooks={len(found)}")
