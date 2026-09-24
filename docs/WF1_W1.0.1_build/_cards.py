import json,os,ssl,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:120]}
LEADS=[("Person-65fa985e (densest, 5 outbound)","f6e3dd60-8537-11f1-ab06-771db760185e"),
       ("Person-5e8cb6df (mid-density, 4)","73a204e0-8528-11f1-a0f4-69afb6784f9c")]
for label,lid in LEADS:
    l=(pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    acts=(pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []
    acts.sort(key=lambda a: str(a.get("due_date") or ""))
    print(f"\n===== {label} =====")
    print(f"lead: {l.get('title')}")
    print(f"activities on card: {len(acts)}")
    for a in acts:
        note=str(a.get("note") or "")
        first=note.splitlines()[0][:70] if note else ""
        print(f"   {a.get('due_date')}  {str(a.get('subject'))[:52]:<52} {'✓' if a.get('done') else '○'}  {first}")
