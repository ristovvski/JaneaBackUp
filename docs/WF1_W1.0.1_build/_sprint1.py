import json,os,ssl,urllib.parse,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=150,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}
SAMPLES=["pii-c1cc5dee@example.invalid","kevin.smith","lnguyen150","tpaul","jclark","golshid.kia"]
print("=== find the sprint leads by title prefix ===")
found=[]
cur=None
for page in range(6):
    q="/v1/leads?limit=100&sort=add_time%20DESC"+(f"&start={page*100}")
    r=pd(q); rows=(r or {}).get("data") or []
    if not rows: break
    for l in rows:
        t=str(l.get("title") or "")
        if t.startswith("3565502 - "):
            found.append(l)
    if len(found)>=8: break
print(f"sprint leads found in recent pages: {len(found)}")
for l in found[:6]:
    print(f"\n  lead {l.get('id')}")
    print(f"    title   ={l.get('title')!r}")
    print(f"    person  ={l.get('person_id')} owner={l.get('owner_id')} creator={l.get('creator_id')}")
    print(f"    add_time={l.get('add_time')} update={l.get('update_time')}")
    print(f"    campaign_field={l.get('1cd81dfcac8a5583935ff4b60e284d0e580db0b6')!r}")
    pid=l.get("person_id")
    if pid:
        p=(pd(f"/api/v2/persons/{pid}") or {}).get("data") or {}
        print(f"    PERSON {pid}: name={p.get('name')!r} first={p.get('first_name')!r} last={p.get('last_name')!r}")
        print(f"      emails={[e.get('value') for e in (p.get('emails') or [])]}")
        print(f"      org={p.get('org_id')} owner={p.get('owner_id')} add={p.get('add_time')}")
