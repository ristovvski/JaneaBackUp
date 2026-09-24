import json,os,ssl,urllib.parse,urllib.request
from collections import Counter,defaultdict
SL=os.environ["SMARTLEAD_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
plan=json.load(open("outbound_backfill_plan_3686181.json",encoding="utf-8"))["plan"]
kc=Counter(p["key"] for p in plan)
dupkeys={k for k,v in kc.items() if v>1}
dupemails={p["email"] for p in plan if p["key"] in dupkeys}
print(f"colliding keys: {len(dupkeys)}  affected leads: {len(dupemails)}  extra entries: {sum(kc[k]-1 for k in dupkeys)}")
# re-pull raw history for those leads and compare every field across the colliding SENTs
off=0; found={}
while off<600 and len(found)<len(dupemails):
    r=sl("/campaigns/3686181/leads-statistics",limit=100,offset=off)
    rows=(r or {}).get("data") or []
    if not rows: break
    for row in rows:
        to=str(row.get("to") or "").lower()
        if to in dupemails: found[to]=row
    if not r.get("hasMore"): break
    off+=100
print(f"raw rows recovered: {len(found)}/{len(dupemails)}\n")
FIELDS=("stats_id","message_id","time","email_seq_number","subject","open_count","click_count")
for em,row in found.items():
    sents=[h for h in (row.get("history") or []) if str(h.get("type")).upper()=="SENT"]
    by=defaultdict(list)
    for h in sents: by[h.get("stats_id")].append(h)
    for sid,group in by.items():
        if len(group)<2: continue
        print(f"=== {em}  stats_id={sid}  x{len(group)} ===")
        for f in FIELDS:
            vals=[str(h.get(f))[:52] for h in group]
            uniq="UNIQUE" if len(set(vals))==len(vals) else ("same" if len(set(vals))==1 else "partial")
            print(f"   {f:<18} {uniq:<7} {vals}")
        bodies=[str(h.get('email_body'))[:40] for h in group]
        print(f"   {'email_body':<18} {'UNIQUE' if len(set(bodies))==len(bodies) else 'same':<7} {bodies}")
        print()
