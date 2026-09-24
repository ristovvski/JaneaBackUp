import json,os,ssl,urllib.parse,urllib.request,hashlib
from collections import defaultdict
SL=os.environ["SMARTLEAD_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
groups=defaultdict(list); off=0
while off<3000:
    r=sl("/campaigns/3686184/leads-statistics",limit=100,offset=off)
    rows=(r or {}).get("data") or []
    if not rows: break
    for row in rows:
        to=str(row.get("to") or "").lower()
        for h in (row.get("history") or []):
            if str(h.get("type")).upper()!="SENT": continue
            groups[(to,h.get("message_id"))].append(h)
    if not r.get("hasMore"): break
    off+=100
dups={k:v for k,v in groups.items() if len(v)>1}
print(f"(lead,message_id) groups with >1 entry: {len(dups)}")
for (to,mid),g in dups.items():
    bodies={hashlib.sha1(str(h.get('email_body')).encode()).hexdigest()[:10] for h in g}
    times={str(h.get('time')) for h in g}
    subs={str(h.get('subject')) for h in g}
    seqs={str(h.get('email_seq_number')) for h in g}
    print(f"\n  {to}  x{len(g)}")
    print(f"    message_id : {str(mid)[:60]}")
    print(f"    times      : {times}")
    print(f"    seq        : {seqs}   subjects: {list(subs)[:2]}")
    print(f"    body hashes: {bodies}  -> {'IDENTICAL rows (feed duplicate)' if len(bodies)==1 and len(times)==1 else 'DISTINCT content'}")
