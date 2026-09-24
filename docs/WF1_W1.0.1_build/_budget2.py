import json,os,ssl,urllib.parse,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; HR=os.environ.get("HEYREACH_API_KEY")
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
print("=== Pipedrive rate-limit headers ===")
for path in ("/v1/users/me","/api/v2/deals?limit=1"):
    try:
        r=urllib.request.Request("https://api.pipedrive.com"+path,headers={"x-api-token":PDT,"User-Agent":"janea/1.0"})
        with urllib.request.urlopen(r,timeout=90,context=ctx) as x:
            h={k.lower():v for k,v in x.headers.items()}
        rel={k:v for k,v in h.items() if "rate" in k or "limit" in k or "budget" in k or "daily" in k}
        print(f"  {path}: {rel if rel else 'no rate headers returned'}")
    except Exception as e: print(f"  {path}: {str(e)[:100]}")

print("\n=== HeyReach AI4 campaigns: outbound message volume ===")
def hr(p,b):
    r=urllib.request.Request("https://api.heyreach.io/api/public"+p,method="POST",data=json.dumps(b).encode(),
        headers={"X-API-KEY":HR,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:150]}
tot_conv=0; tot_msgs=0; tot_out=0; off=0; pages=0; per_camp={}
while pages<8:
    c=hr("/inbox/GetConversationsV2",{"filters":{},"offset":off,"limit":100})
    items=(c or {}).get("items") or []
    if not items: break
    if pages==0: print(f"  totalCount reported: {c.get('totalCount')}")
    for x in items:
        tot_conv+=1
        msgs=x.get("messages") or []
        tot_msgs+=len(msgs)
        out=[m for m in msgs if m.get("sender")=="ME"]
        tot_out+=len(out)
    off+=100; pages+=1
    if off>= (c.get("totalCount") or 0): break
print(f"  conversations walked: {tot_conv} over {pages} page(s)")
print(f"  messages total: {tot_msgs}   OUTBOUND (sender=ME): {tot_out}")
print(f"  -> avg {tot_msgs/max(1,tot_conv):.1f} msgs/conversation, {tot_out/max(1,tot_conv):.1f} outbound")
