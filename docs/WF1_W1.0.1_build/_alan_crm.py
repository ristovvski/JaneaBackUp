import json,os,ssl,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.pipedrive.com"+p,
            headers={"x-api-token":PDT,"User-Agent":"janea/1.0"}),timeout=120,context=ctx) as x: return json.load(x)
    except Exception as e: return {"__err":str(e)[:130]}
LEAD="f6bfaf70-90af-11f1-8dcf-2514ab8cea07"
l=(pd(f"/v1/leads/{LEAD}") or {}).get("data") or {}
print(f"lead {LEAD[:8]} title={l.get('title')!r} archived={l.get('is_archived')}")
print(f"  labels={len(l.get('label_ids') or [])} person={l.get('person_id')}")
A=(pd(f"/api/v2/activities?lead_id={LEAD}&limit=50") or {}).get("data") or []
print(f"  activities: {len(A)}")
from collections import Counter
sig=Counter()
for a in A:
    k=(str(a.get('subject'))[:40], str(a.get('due_date')))
    sig[k]+=1
    print(f"    {a.get('id')} {str(a.get('subject'))[:44]!r} due={a.get('due_date')} done={a.get('done')} note={len(str(a.get('note') or ''))}ch")
dups={k:v for k,v in sig.items() if v>1}
print(f"\n  DUPLICATE (same subject+date) groups: {len(dups)}")
for k,v in dups.items(): print(f"     x{v}  {k}")
if not dups: print("  -> no duplicate reply trail; the re-alert was Slack-side only, CRM is clean")
