import json,os,ssl,urllib.parse,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; SL=os.environ["SMARTLEAD_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
print("=== Pipedrive rate-limit headers (the real budget, not a guess) ===")
r=urllib.request.Request("https://api.pipedrive.com/api/v2/users/me",
    headers={"x-api-token":PDT,"User-Agent":"janea/1.0"})
try:
    with urllib.request.urlopen(r,timeout=90,context=ctx) as x:
        h=dict(x.headers); body=json.load(x)
    for k,v in sorted(h.items()):
        if any(t in k.lower() for t in ("ratelimit","rate-limit","daily","budget","x-")): print(f"   {k}: {v}")
    d=body.get("data") or {}
    print(f"   company={d.get('company_name')!r} user={d.get('name')!r}")
except Exception as e: print("  ",str(e)[:160])

print("\n=== Smartlead AI4 campaigns: sent volume ===")
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
tot=0
for cid in (3686181,3686184,3686187,3686193):
    c=sl(f"/campaigns/{cid}")
    nm=str((c or {}).get("name") or "?")[:46]
    a=sl(f"/campaigns/{cid}/analytics")
    if isinstance(a,dict) and not a.get("__err"):
        sent=a.get("sent_count") or a.get("sent") or a.get("total_sent")
        print(f"  {cid} {nm!r}")
        print(f"     analytics keys: {sorted(list(a.keys()))[:12]}")
        print(f"     sent={sent} unique_sent={a.get('unique_sent_count')} replies={a.get('reply_count')}")
        try: tot+=int(sent or 0)
        except Exception: pass
    else:
        print(f"  {cid} {nm!r}: analytics {a.get('__err')}")
print(f"\n  AI4 email SENT total (from analytics): {tot}")
