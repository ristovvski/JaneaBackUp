import json,os,re,ssl,urllib.parse,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; SL=os.environ["SMARTLEAD_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
def sl(p,**q):
    q["api_key"]=SL
    with urllib.request.urlopen(urllib.request.Request(
        "https://server.smartlead.ai/api/v1"+p+"?"+urllib.parse.urlencode(q),
        headers={"User-Agent":"janea/1.0"}),timeout=180,context=ctx) as x: return json.load(x)
rk=json.load(open("rekey_plan_3686181.json",encoding="utf-8"))["todo"]
t=rk[0]
print(f"re-key sample: activity {t['activity']}  new key we wrote: {t['new']!r}")
a=(pd(f"/api/v2/activities/{t['activity']}") or {}).get("data") or {}
note=str(a.get("note") or "")
m=re.search(r"\[key:([^\]]+)\]",note)
print(f"key NOW in the live note: {m.group(1)!r}" if m else "NO KEY FOUND IN LIVE NOTE")
print(f"note tail: {note[-120:]!r}")
print(f"\nactivity lead_id={a.get('lead_id')}")
# what key would the new plan compute for this same send?
r=sl("/campaigns/3686181/leads-statistics",limit=100,offset=0)
for row in (r.get("data") or []):
    for h in (row.get("history") or []):
        if str(h.get("type")).upper()!="SENT": continue
        k=f"O|SL|{h.get('message_id')}"
        if k==t["new"]:
            print(f"plan would compute : {k!r}")
            print(f"MATCH: {k==(m.group(1) if m else None)}")
            raise SystemExit
print("(sample send not on page 1 - showing generic comparison)")
