import json,os,ssl,urllib.request
from collections import Counter,defaultdict
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
plan=json.load(open("outbound_backfill_plan_3686181.json",encoding="utf-8"))["plan"]
print("=== 1. is stats_id actually unique in the plan? ===")
kc=Counter(p["key"] for p in plan)
dup={k:v for k,v in kc.items() if v>1}
print(f"  plan entries: {len(plan)}   distinct keys: {len(kc)}   keys used more than once: {len(dup)}")
for k,v in list(dup.items())[:5]:
    ems={p['email'] for p in plan if p['key']==k}
    print(f"    {k}  x{v}  emails={ems}")
print("\n=== 2. did activities land on the RIGHT campaign's lead? ===")
F="1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
lids={p["body"]["lead_id"] for p in plan}
right=wrong=blank=0; examples=[]
for i,lid in enumerate(lids,1):
    l=(pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    camp=str(l.get(F) or "")
    if not camp: blank+=1
    elif "AI4 2026 - Mario - Valids" in camp: right+=1
    else:
        wrong+=1
        if len(examples)<6: examples.append((str(l.get('title'))[:62],camp[:44]))
    if i%80==0: print(f"  ...{i}/{len(lids)}")
print(f"  leads targeted: {len(lids)}")
print(f"    campaign field matches 3686181 : {right}")
print(f"    campaign field is a DIFFERENT campaign : {wrong}")
print(f"    campaign field blank : {blank}")
for t,c in examples: print(f"      MISMATCH lead={t!r}  field={c!r}")
