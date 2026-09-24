import json,os,ssl,urllib.parse,urllib.request
from collections import Counter
SL=os.environ["SMARTLEAD_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}
r=sl("/campaigns/3686181/leads-statistics",limit=100,offset=0)
rows=(r or {}).get("data") or []
print(f"rows page 1: {len(rows)}  hasMore={r.get('hasMore')}")
types=Counter(); sample=None
for row in rows:
    for h in (row.get("history") or []):
        t=str(h.get("type") or h.get("event_type") or "?")
        types[t]+=1
        if t.upper().startswith("SENT") and sample is None: sample=(row,h)
print("history entry types:", dict(types))
if sample:
    row,h=sample
    print(f"\nrow keys: {sorted(row.keys())}")
    print(f"  to={row.get('to')!r} lead_id={row.get('lead_id')} from={row.get('from')!r}")
    print(f"\nSENT entry keys: {sorted(h.keys())}")
    for k in sorted(h.keys()):
        v=h[k]
        print(f"   {k:<22} {repr(v)[:110]}")
else:
    print("\nno SENT entry found; first history entry of first row:")
    for row in rows:
        hs=row.get("history") or []
        if hs:
            print(f"  keys: {sorted(hs[0].keys())}")
            print(json.dumps(hs[0],ensure_ascii=False)[:500]); break
