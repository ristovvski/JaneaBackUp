import json,os,ssl,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x:
            return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}
names={str(l.get("id")):l.get("name") for l in ((pd("/v1/leadLabels") or {}).get("data") or [])}
LEAD="fb215d20-94e7-11f1-9c86-a5bfb8f637e5"
l=(pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
ids=l.get("label_ids") or []
print("=== Person-9979a87c lead fb215d20 ===")
print(f"  title={l.get('title')!r} archived={l.get('is_archived')} owner={l.get('owner_id')}")
print(f"  labels ({len(ids)}):")
for i in ids: print(f"     {i}  {names.get(i,'?')!r}")
DNC="52a7c290-fc73-11f0-ad98-81d4703453f3"
print(f"\n  DO NOT CONTACT still present: {DNC in ids}")
print(f"  expectation was Cold+Responded only -> {'MATCHES' if DNC not in ids else 'DNC SURVIVED - do not tell Noah to reply yet'}")
# does the person have an open deal? (1b relevance + is a deal the right home)
d=(pd("/api/v2/deals?person_id=85517&limit=20") or {}).get("data") or []
print(f"\n  person 85517 open deals: {[(x.get('id'),x.get('status'),str(x.get('title'))[:40]) for x in d]}")
A=(pd(f"/api/v2/activities?lead_id={LEAD}&limit=20") or {}).get("data") or []
print(f"  activities on lead: {len(A)}")
for a in A: print(f"     {a.get('id')} {str(a.get('subject'))[:44]!r} due={a.get('due_date')}")
