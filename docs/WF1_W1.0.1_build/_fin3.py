import json,os,ssl,urllib.parse,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; SL=os.environ["SMARTLEAD_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
print("=== the lead WF-2 created on Lara's SENT ===")
l=(pd("/v1/leads/42308ac0-a2d4-11f1-8e86-219530dc474a") or {}).get("data") or {}
print(f"  title      = {l.get('title')!r}")
print(f"  person_id  = {l.get('person_id')!r}   <-- ORPHAN if null")
print(f"  org_id     = {l.get('organization_id')!r}")
print(f"  owner      = {l.get('owner_id')}  add={l.get('add_time')}")
print(f"  labels     = {len(l.get('label_ids') or [])}")
print(f"  campaign_f = {l.get('1cd81dfcac8a5583935ff4b60e284d0e580db0b6')!r}")
print("\n=== person 85825 as created ===")
p=(pd("/api/v2/persons/85825") or {}).get("data") or {}
print(f"  name   = {p.get('name')!r}   <-- email-as-name?")
print(f"  first  = {p.get('first_name')!r} last={p.get('last_name')!r}")
print(f"  emails = {[e.get('value') for e in (p.get('emails') or [])]}")
print("\n=== what Smartlead actually holds for her ===")
g=sl("/leads/",email="pii-c7524b7a@example.invalid")
print(f"  first={g.get('first_name')!r} last={g.get('last_name')!r} company={g.get('company_name')!r}")
print("\n=== how many Finovate leads did WF-2 create so far, and are they orphaned? ===")
start=0; found=[]
while start<400:
    r=pd(f"/v1/leads?limit=100&start={start}&sort=add_time%20DESC")
    rows=(r or {}).get("data") or []
    if not rows: break
    for x in rows:
        t=str(x.get("title") or "")
        if t.startswith("3868449 - ") or t.startswith("3868450 - "): found.append(x)
    more=((r.get("additional_data") or {}).get("pagination") or {})
    if not more.get("more_items_in_collection"): break
    start=more.get("next_start") or (start+100)
print(f"  Finovate-titled leads: {len(found)}")
orph=[x for x in found if not x.get("person_id")]
print(f"  orphaned (person_id null): {len(orph)}")
for x in found[:6]:
    print(f"     {str(x.get('id'))[:8]} person={x.get('person_id')} {str(x.get('title'))[:52]!r}")
