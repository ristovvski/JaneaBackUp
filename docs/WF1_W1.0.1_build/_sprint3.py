import json,os,ssl,urllib.parse,urllib.request
SL=os.environ["SMARTLEAD_API_KEY"]; PDT=os.environ["PIPEDRIVE_API_TOKEN"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:160]}
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=150,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}

print("=== is 3565502 a Smartlead campaign? ===")
c=sl("/campaigns/3565502")
if isinstance(c,dict) and not c.get("__err"):
    print(f"  id={c.get('id')} name={c.get('name')!r} status={c.get('status')} created={c.get('created_at')}")
else: print("  ",c)

print("\n=== global Smartlead lead lookup by email (source of truth for names) ===")
for em in ("pii-c1cc5dee@example.invalid","pii-5a90b531@example.invalid","pii-86086c31@example.invalid"):
    r=sl("/leads/",email=em)
    if isinstance(r,dict) and r.get("__err"): print(f"  {em}: {r['__err']}"); continue
    d=r if isinstance(r,dict) else {}
    print(f"  {em}: first={d.get('first_name')!r} last={d.get('last_name')!r} "
          f"company={str(d.get('company_name'))[:24]!r} id={d.get('id')}")

print("\n=== calibrate creator_id: leads WE created today vs the sprint burst ===")
for lid,label in (("76be46a0-97cc-11f1-9193-c561bf0178a0","Andrea repair (my API token, today)"),
                  ("aa567010-95a5-11f1-9f42-1b0d869912a8","sprint lead kevin.smith")):
    l=(pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    print(f"  {label}: creator_id={l.get('creator_id')} owner={l.get('owner_id')} add={l.get('add_time')}")
print("\n=== who is user 25112064 / 16340280? ===")
for uid in (25112064,16340280,25733113):
    u=(pd(f"/v1/users/{uid}") or {}).get("data") or {}
    print(f"  {uid}: name={u.get('name')!r} email={u.get('email')!r} active={u.get('active_flag')}")
