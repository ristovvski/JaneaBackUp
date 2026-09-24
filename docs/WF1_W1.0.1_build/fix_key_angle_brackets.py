#!/usr/bin/env python3
"""URGENT CORRECTIVE - the re-key wrote message_id WITH its RFC angle brackets into the note, and
Pipedrive's note field is HTML: `<ea0a107e-...@domain>` was parsed as a tag and stripped. All 983
notes now read `[key:O|SL|]` - an empty, identical key on every activity. Idempotency is not merely
weakened, it is inverted: every key matches every other, so a re-run would either skip everything or
duplicate everything depending on which side you read.

FIX: the canonical key uses message_id with the angle brackets stripped:
    O|SL|pii-0ae439d1@example.invalid

Repairs from the rekey artifact (activity id -> intended key), because the live notes no longer
carry anything to match on. Lesson for the doc: any identifier written into a Pipedrive note must be
HTML-safe - the note is not a plain-text field.
"""
import json,os,re,ssl,sys,time,urllib.request
PDT=os.environ["PIPEDRIVE_API_TOKEN"]; CA=os.environ.get("REQUESTS_CA_BUNDLE")
ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE=os.path.dirname(os.path.abspath(__file__))
LIVE="--live" in sys.argv
def pd(p,method="GET",body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request("https://api.pipedrive.com"+p,method=method,data=data,
        headers={"x-api-token":PDT,"Content-Type":"application/json","User-Agent":"janea/1.0"})
    try:
        with urllib.request.urlopen(r,timeout=120,context=ctx) as x: return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err":f"HTTP {e.code} {e.read()[:200].decode('utf-8','replace')}"}
    except Exception as e: return {"__err":str(e)[:140]}
def safe(mid): return str(mid).strip().lstrip("<").rstrip(">")
todo=json.load(open(os.path.join(HERE,"rekey_plan_3686181.json"),encoding="utf-8"))["todo"]
print(f"activities to repair: {len(todo)}")
fixed=[]
for t in todo:
    mid=t["new"].split("|",2)[2]
    newkey=f"O|SL|{safe(mid)}"
    fixed.append({"activity":t["activity"],"key":newkey})
keys=[f["key"] for f in fixed]
print(f"distinct sanitised keys: {len(set(keys))}/{len(keys)}")
print(f"any still containing < or > : {sum(1 for k in keys if '<' in k or '>' in k)}")
for f in fixed[:3]: print(f"   {f['activity']}  {f['key']}")
if not LIVE:
    print("\ndry-run: nothing written."); sys.exit(0)
print("\n=== REPAIRING ===")
ok=fail=0
for i,f in enumerate(fixed,1):
    a=(pd(f"/api/v2/activities/{f['activity']}") or {}).get("data") or {}
    note=str(a.get("note") or "")
    if "[key:" in note: note=re.sub(r"\[key:[^\]]*\]",f"[key:{f['key']}]",note,count=1)
    else: note=note.rstrip()+f"\n\n[key:{f['key']}]"
    r=pd(f"/api/v2/activities/{f['activity']}","PATCH",{"note":note})
    if r.get("__err"):
        fail+=1
        if fail<=3: print(f"  FAIL {f['activity']}: {r['__err'][:110]}")
    else: ok+=1
    if i%150==0: print(f"  ...{i}/{len(fixed)} ok={ok} fail={fail}"); time.sleep(1)
print(f"\nREPAIRED {ok}  failed {fail}")
# readback sample
s=(pd(f"/api/v2/activities/{fixed[0]['activity']}") or {}).get("data") or {}
m=re.search(r"\[key:([^\]]+)\]",str(s.get("note") or ""))
print(f"readback sample key: {m.group(1)!r}" if m else "readback: NO KEY")
