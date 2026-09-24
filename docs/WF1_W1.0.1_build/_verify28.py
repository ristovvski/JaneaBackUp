import json,os,re,ssl,urllib.request
from collections import Counter,defaultdict
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
plan=json.load(open("outbound_backfill_plan_3686181.json",encoding="utf-8"))["plan"]
want=defaultdict(set)
for p in plan: want[p["body"]["lead_id"]].add(p["key"])
print(f"plan: {len(plan)} activities across {len(want)} leads")
found=0; missing=[]; dupes=0; per=[]
for i,(lid,keys) in enumerate(want.items(),1):
    acts=(pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []
    got=Counter()
    for a in acts:
        m=re.search(r"\[key:([^\]]+)\]",str(a.get("note") or ""))
        if m: got[m.group(1)]+=1
    for k in keys:
        if got.get(k,0)>=1: found+=1
        else: missing.append((lid,k))
        if got.get(k,0)>1: dupes+=1
    per.append(len([a for a in acts if "→ SENT via campaign" in str(a.get("note") or "")]))
    if i%60==0: print(f"  ...{i}/{len(want)} verified")
print(f"\nkeys present in Pipedrive : {found}/{len(plan)}")
print(f"missing                   : {len(missing)}")
print(f"duplicate keys            : {dupes}")
print(f"outbound activities/lead  : min={min(per)} max={max(per)} avg={sum(per)/len(per):.1f}")
c=Counter(per); print(f"distribution              : {dict(sorted(c.items()))}")
top=sorted(zip(want.keys(),per),key=lambda t:-t[1])[:3]
print("\ndensest leads (for screenshots):")
for lid,n in top:
    l=(pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    print(f"   {n} outbound · {l.get('title')!r}")
    print(f"      https://janeasystems.pipedrive.com/leads/inbox/{lid}")
