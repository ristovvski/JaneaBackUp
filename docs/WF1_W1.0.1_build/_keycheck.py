import json,os,ssl,urllib.parse,urllib.request
from collections import Counter
SL=os.environ["SMARTLEAD_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
CAMPS=[3686181,3686184,3686187,3686193]
for cid in CAMPS:
    sids=[]; mids=[]; st=[]; miss_mid=0
    off=0
    while off<3000:
        r=sl(f"/campaigns/{cid}/leads-statistics",limit=100,offset=off)
        rows=(r or {}).get("data") or []
        if not rows: break
        for row in rows:
            to=str(row.get("to") or "").lower()
            for h in (row.get("history") or []):
                if str(h.get("type")).upper()!="SENT": continue
                sid=h.get("stats_id"); mid=h.get("message_id"); t=h.get("time")
                sids.append((to,sid)); mids.append((to,mid)); st.append((to,sid,t))
                if not mid: miss_mid+=1
        if not r.get("hasMore"): break
        off+=100
    n=len(sids)
    print(f"campaign {cid}: {n} SENT")
    print(f"   distinct (lead,stats_id)          : {len(set(sids))}   collisions={n-len(set(sids))}")
    print(f"   distinct (lead,message_id)        : {len(set(mids))}   collisions={n-len(set(mids))}")
    print(f"   distinct (lead,stats_id,time)     : {len(set(st))}   collisions={n-len(set(st))}")
    print(f"   SENT lacking message_id           : {miss_mid}")
    gm=Counter(m for _,m in mids)
    print(f"   message_id GLOBALLY unique        : {len([1 for v in gm.values() if v>1])==0}")
