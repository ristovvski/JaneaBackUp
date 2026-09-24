import json,os,ssl,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x:
            return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}

print("=== deals for person 69696 (Andrea) ===")
d=pd("/api/v2/deals?person_id=69696&limit=50")
for x in (d.get("data") or []):
    print(f"  deal {x.get('id')} title={str(x.get('title'))[:50]!r} status={x.get('status')} "
          f"stage={x.get('stage_id')} pipeline={x.get('pipeline_id')} added={x.get('add_time')} "
          f"owner={x.get('owner_id')} value={x.get('value')}")
print(f"  err={d.get('__err')}")

print("\n=== deal 2093 direct ===")
d2=pd("/api/v2/deals/2093"); dd=(d2 or {}).get("data") or {}
print(f"  title={dd.get('title')!r} person={dd.get('person_id')} org={dd.get('org_id')} "
      f"status={dd.get('status')} stage={dd.get('stage_id')} added={dd.get('add_time')} "
      f"update={dd.get('update_time')}")

print("\n=== leads for person 69696 ===")
L=(pd("/v1/leads?limit=50&person_id=69696") or {}).get("data") or []
for l in L:
    print(f"  lead {l.get('id')} title={str(l.get('title'))[:56]!r} archived={l.get('is_archived')} "
          f"labels={len(l.get('label_ids') or [])} add={l.get('add_time')}")

print("\n=== activities on the repair lead 76be46a0 ===")
A=(pd("/api/v2/activities?lead_id=76be46a0-97cc-11f1-9193-c561bf0178a0&limit=20") or {}).get("data") or []
for a in A:
    print(f"  activity {a.get('id')} {str(a.get('subject'))[:44]!r} done={a.get('done')} "
          f"due={a.get('due_date')} note={len(str(a.get('note') or ''))}ch deal={a.get('deal_id')} person={a.get('person_id')}")

print("\n=== activities already on deal 2093 ===")
A2=(pd("/api/v2/activities?deal_id=2093&limit=20") or {}).get("data") or []
print(f"  count={len(A2)}")
for a in A2[:6]:
    print(f"  {a.get('id')} {str(a.get('subject'))[:44]!r} due={a.get('due_date')}")
