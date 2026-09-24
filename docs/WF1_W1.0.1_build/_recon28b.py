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
def hr(path,method="POST",body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request("https://api.heyreach.io/api/public"+path,method=method,data=data,
        headers={"X-API-KEY":HR,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=120,context=ctx) as x: return json.load(x)
    except urllib.error.HTTPError as e: return {"__err":f"HTTP {e.code} {e.read()[:250].decode('utf-8','replace')}"}
    except Exception as e: return {"__err":str(e)[:150]}

print("=== a sample message_sent webhook payload ===")
cur=None; pages=0; shown=0; alan=[]
while pages<8 and shown<1:
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
        if shown<1:
            shown=1
            print(f"  exec {r['id']} {r.get('startedAt')}")
            print(f"  top-level keys: {sorted(raw.keys())}")
            for k in ("event_type","campaign","sender","lead","message","recent_messages",
                      "conversation_id","external_reference","timestamp","is_inmail"):
                v=raw.get(k)
                print(f"    {k:<20} {json.dumps(v,ensure_ascii=False)[:170] if v is not None else 'ABSENT'}")
    cur=d.get("nextCursor"); pages+=1
    if not cur: break

print("\n=== does a manual UI send appear? Person-2f078c2e thread from the INBOX API ===")
conv=hr("/inbox/GetConversationsV2",body={"filters":{"leadLinkedInId":None},"offset":0,"limit":100})
items=(conv or {}).get("items") or []
print(f"  conversations fetched: {len(items)} of {conv.get('totalCount')}")
hit=None
for c in items:
    blob=json.dumps(c,ensure_ascii=False).lower()
    if "alan" in blob and "wang" in blob: hit=c; break
if not hit:
    print("  Alan not in the first page; conversation object shape from item[0]:")
    hit=items[0] if items else None
if hit:
    print(f"  conversation keys: {sorted(hit.keys())}")
    msgs=hit.get("messages") or hit.get("recentMessages") or []
    print(f"  messages in object: {len(msgs)}")
    for m in (msgs[:6] if isinstance(msgs,list) else []):
        print(f"    {json.dumps(m,ensure_ascii=False)[:200]}")
