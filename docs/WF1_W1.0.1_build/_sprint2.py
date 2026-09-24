import json,os,re,ssl,urllib.parse,urllib.request
SL=os.environ["SMARTLEAD_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def sl(p,**q):
    q["api_key"]=SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
            "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
            headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:140]}
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
print("=== SOURCE: Smartlead campaign 3565502 lead records ===")
TARGETS={"pii-c1cc5dee@example.invalid","pii-5a90b531@example.invalid","pii-86086c31@example.invalid",
         "pii-bc41bcbd@example.invalid","pii-bed9f689@example.invalid"}
off=0; seen=0; hits=0
while off<600:
    r=sl("/campaigns/3565502/leads",limit=100,offset=off)
    rows=(r or {}).get("data") or []
    if not rows: break
    for row in rows:
        seen+=1
        ld=row.get("lead") or row
        em=str(ld.get("email") or "").lower()
        if em in TARGETS:
            hits+=1
            print(f"\n  {em}")
            for k in ("first_name","last_name","company_name","linkedin_profile","website",
                      "phone_number","location"):
                print(f"     {k:<18} {repr(ld.get(k))[:60]}")
            cf=ld.get("custom_fields") or {}
            print(f"     custom_fields keys: {list(cf.keys())[:8]}")
    off+=100
    if hits>=3: break
print(f"\n  scanned {seen} campaign leads, matched {hits}")

print("\n=== OUR WRITE: how Normalize builds full_name ===")
wf=n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv"); N={n["name"]:n for n in wf["nodes"]}
js=N["Normalize"]["parameters"]["jsCode"]
for i,l in enumerate(js.splitlines(),1):
    if re.search(r"full_name|first_name|last_name|localOf|split\('@'\)",l):
        print(f"  {i:>3}| {l.rstrip()[:110]}")
print("\n=== and Apply Enrich (the other name source) ===")
if "Apply Enrich" in N:
    js2=N["Apply Enrich"]["parameters"].get("jsCode","")
    for i,l in enumerate(js2.splitlines(),1):
        if re.search(r"full_name|first_name|last_name|@",l): print(f"  {i:>3}| {l.rstrip()[:110]}")
