import json,os,ssl,sys,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
LIVE="--live" in sys.argv
LEAD="76be46a0-97cc-11f1-9193-c561bf0178a0"; DEAL=2093; PERSON=69696
def pd(p,method="GET",body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request("https://api.pipedrive.com"+p,method=method,data=data,
        headers={"x-api-token":PDT,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=120,context=ctx) as x: return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err":f"HTTP {e.code} {e.read()[:250].decode('utf-8','replace')}"}

src=(pd("/api/v2/activities/44140") or {}).get("data") or {}
note=str(src.get("note") or "")
print(f"source activity 44140: subject={src.get('subject')!r} due={src.get('due_date')} note={len(note)}ch")
if not note: sys.exit("no note on 44140 - refusing to move an empty record")

new_note=("[Moved from a duplicate lead, 2026-08-18] Andrea is already represented by this OPEN DEAL. "
          "My 2026-08-14 repair created a separate lead because the person showed 0 LEADS - true, and "
          "misleading: a person converted to a deal has no leads. The reply belongs here.\n\n"+note)
act={"subject":"Email reply — [Events Visiting] HumanX 2026 - Valids","type":"email","done":True,
     "owner_id":src.get("owner_id") or 16340280,"deal_id":DEAL,"participants":[{"person_id":PERSON,"primary":True}],
     "note":new_note,"due_date":src.get("due_date") or "2026-08-13"}
print(f"\nPLAN:\n 1. POST activity onto deal {DEAL} (note {len(new_note)}ch)\n"
      f" 2. DELETE activity 44140 from the duplicate lead\n"
      f" 3. ARCHIVE lead {LEAD}  (archive, NOT delete - reversible)\n"
      f" 4. leave Handover 44141 alone; report it\n")
if not LIVE:
    print("dry-run: nothing written."); sys.exit(0)

r1=pd("/api/v2/activities","POST",act)
nid=(r1.get("data") or {}).get("id")
if r1.get("__err") or not nid: sys.exit(f"deal activity FAILED: {r1.get('__err')}")
print(f"  created activity {nid} on deal {DEAL}")
back=(pd(f"/api/v2/activities?deal_id={DEAL}&limit=30") or {}).get("data") or []
if not any(a.get("id")==nid for a in back): sys.exit("readback: new activity NOT on the deal - stopping before any removal")
print(f"  readback OK: deal now has {len(back)} activities")

r2=pd("/api/v2/activities/44140","DELETE")
print(f"  removed 44140 from the duplicate lead: {'ERR '+str(r2.get('__err')) if r2.get('__err') else 'ok'}")
r3=pd(f"/v1/leads/{LEAD}","PATCH",{"is_archived":True})
print(f"  archive lead: {'ERR '+str(r3.get('__err')) if r3.get('__err') else ((r3.get('data') or {}).get('is_archived'))}")
L=(pd("/v1/leads?limit=50&person_id=69696&archived_status=all") or {}).get("data") or []
for l in L: print(f"  READBACK lead {l.get('id')} archived={l.get('is_archived')}")
print(f"  deal activities now: {len((pd(f'/api/v2/activities?deal_id={DEAL}&limit=30') or {}).get('data') or [])}")
