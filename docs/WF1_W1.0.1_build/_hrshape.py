import json,os,ssl,urllib.request
HR=os.environ["HEYREACH_API_KEY"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def hr(p,b):
    r=urllib.request.Request("https://api.heyreach.io/api/public"+p,method="POST",
        data=json.dumps(b).encode(),headers={"X-API-KEY":HR,"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=180,context=ctx) as x: return json.load(x)
r=hr("/campaign/GetLeadsFromCampaign",{"campaignId":572715,"offset":0,"limit":3})
print("top-level keys:",sorted(r.keys()),"total=",r.get("totalCount"))
items=r.get("items") or []
print(f"items: {len(items)}")
if items:
    print("ITEM 0 keys:",sorted(items[0].keys()))
    print(json.dumps(items[0],ensure_ascii=False)[:700])
