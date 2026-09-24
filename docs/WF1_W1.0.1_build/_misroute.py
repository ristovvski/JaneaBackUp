import json,os,ssl,urllib.request
from collections import defaultdict
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
new=json.load(open("outbound_backfill_plan_3686181.json",encoding="utf-8"))["plan"]
# current plan = only the 121 still "missing"; group by lead
byleadnew=defaultdict(list)
for p in new: byleadnew[p["body"]["lead_id"]].append(p["email"])
print(f"activities the corrected routing wants to (re)write: {len(new)}")
print(f"distinct destination leads: {len(byleadnew)}")
emails=sorted({p['email'] for p in new})
print(f"distinct affected people: {len(emails)}\n")
F="1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
shown=0
for lid,ems in byleadnew.items():
    l=(pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    pidv=l.get("person_id")
    allleads=(pd(f"/v1/leads?limit=50&person_id={pidv}") or {}).get("data") or []
    act=[x for x in allleads if not x.get("is_archived")]
    print(f"person {pidv} · {ems[0]} · {len(ems)} activities")
    print(f"   CORRECT dest : {str(l.get('title'))[:60]!r}  campaign_field={str(l.get(F) or '')[:30]!r}")
    for x in act:
        if x.get("id")==lid: continue
        a=(pd(f"/api/v2/activities?lead_id={x.get('id')}&limit=100") or {}).get("data") or []
        n=len([y for y in a if "→ SENT via campaign" in str(y.get("note") or "")])
        if n: print(f"   HOLDS {n:>2} outbound now: {str(x.get('title'))[:56]!r}")
    shown+=1
    if shown>=6: print(f"   ... ({len(byleadnew)-6} more)"); break
