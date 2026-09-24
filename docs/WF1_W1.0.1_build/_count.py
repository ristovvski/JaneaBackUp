import json,os,re,ssl,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
tot={}; start=0; pages=0
while pages<60:
    r=pd(f"/v1/leads?limit=100&start={start}&sort=add_time%20DESC")
    rows=(r or {}).get("data") or []
    if not rows: break
    for l in rows:
        t=str(l.get("title") or "")
        for cid in ("3565502","3565651"):
            if t.startswith(cid+" - "):
                tail=t.rsplit(" - ",1)[-1]
                tot.setdefault(cid,[]).append(tail)
    more=((r.get("additional_data") or {}).get("pagination") or {})
    if not more.get("more_items_in_collection"): break
    start=more.get("next_start") or (start+100); pages+=1
for cid,names in tot.items():
    localish=[n for n in names if " " not in n]
    print(f"  campaign {cid}: {len(names)} leads, {len(localish)} with a local-part-style name ({100*len(localish)//max(1,len(names))}%)")
    print(f"     sample: {localish[:6]}")
print(f"  pages walked: {pages}  (stopped on more_items_in_collection=false)" )
