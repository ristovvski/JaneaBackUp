import json,os,ssl,urllib.parse,urllib.request
from collections import Counter
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
def hr(path,method="GET",body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request("https://api.heyreach.io/api/public"+path,method=method,data=data,
        headers={"X-API-KEY":HR,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=120,context=ctx) as x: return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err":f"HTTP {e.code} {e.read()[:200].decode('utf-8','replace')}"}
    except Exception as e: return {"__err":str(e)[:150]}

print("=== 1. WF-1 event types actually received (webhook payloads) ===")
ev=Counter(); cur=None; pages=0
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
        ev[str(raw.get("event_type") or raw.get("eventType") or "?")]+=1
    cur=d.get("nextCursor"); pages+=1
    if not cur: break
print(f"  pages walked: {pages}")
for k,v in ev.most_common(): print(f"    {k:<42} {v}")

print("\n=== 2. HeyReach: is there an outbound/message-sent event or a thread API? ===")
for p,m,b in (("/webhook/GetAll","POST",{"offset":0,"limit":50}),
              ("/webhooks/GetAll","POST",{"offset":0,"limit":50}),
              ("/inbox/GetConversationsV2","POST",{"filters":{},"offset":0,"limit":2}),
              ("/inbox/GetConversations","POST",{"offset":0,"limit":2})):
    r=hr(p,m,b)
    if isinstance(r,dict) and r.get("__err"): print(f"  {p}: {r['__err'][:90]}")
    else: print(f"  {p}: keys={sorted(list(r.keys()))[:8]}  total={r.get('totalCount')}")
