#!/usr/bin/env python3
"""Registry seed, STEP 1 — build the seed list as an artifact. Reads only; writes a JSON file.

Source is EXECUTION HISTORY, not the Slack harvest: the missing alerts were delivered to
#niks-channel and were never in #lead-processing, and the execution carries the exact __alert_key
next to ok:true and the destination channel. Authoritative rather than reconstructed.

Evidence rule for THIS harvest: ok:true on ANY channel counts as delivered. That is the rule of the
era being rebuilt - before 2026-08-11 the team channel was not the destination, so scoring old
alerts against it is what dropped ~20 keys in the first place.

Pages with the cursor to exhaustion. A capped read here would silently under-seed, and an
under-seeded registry looks exactly like a correct one until someone replies.
"""
import json,os,ssl,urllib.parse,urllib.request
from collections import Counter
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
SPECS=[("2jdjKM2NJr473GdA","WF-1",[("M7 Alert Gate","M7 Critical Slack")]),
       ("jp7rum9Z0YDJkQWv","WF-2",[("First Reply Gate","Reply Alert"),("First Reply Gate","Nurture Alert")])]
seed={}; chans=Counter(); pages_total=0; execs_total=0
for wid,label,pairs in SPECS:
    cur=None; pages=0
    while pages<40:
        q={"workflowId":wid,"limit":250}
        if cur: q["cursor"]=cur
        d=n8n("/api/v1/executions?"+urllib.parse.urlencode(q)) or {}
        rows=d.get("data") or []
        if not rows: break
        for r in rows:
            execs_total+=1
            if str(r.get("startedAt") or "")[:10] < "2026-08-05": continue
            det=n8n(f"/api/v1/executions/{r['id']}?includeData=true")
            rd=((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
            if not rd: continue
            def o(nm):
                try: return rd[nm][0]["data"]["main"][0][0]["json"]
                except Exception: return None
            for gate,alert in pairs:
                al=o(alert)
                if not al or al.get("ok") is not True: continue
                g=o(gate) or {}
                k=g.get("__alert_key")
                if not k: continue
                ch=al.get("channel")
                chans[str(ch)]+=1
                prev=seed.get(k)
                stamp=r.get("startedAt")
                if not prev or str(stamp)<str(prev["at"]):
                    seed[k]={"at":stamp,"channel":ch,"wf":label,"exec":r["id"]}
        cur=d.get("nextCursor"); pages+=1; pages_total+=1
        if not cur: break
    print(f"{label}: {pages} page(s) walked")
print(f"\nexecutions examined: {execs_total}")
print(f"distinct alert keys with ok:true (any channel): {len(seed)}")
print("deliveries by channel:", dict(chans))
NAME={"C07LTD8UT70":"#lead-processing","C0B8GCVNR5W":"#niks-channel"}
byday=Counter(v["at"][:10] for v in seed.values())
print("first-delivery by day:", dict(sorted(byday.items())))
pre=[k for k,v in seed.items() if str(v["channel"])!="C07LTD8UT70"]
print(f"keys whose FIRST delivery was NOT the team channel (the dropped class): {len(pre)}")
ALAN="Lf6bfaf70-90af-11f1-8dcf-2514ab8cea07|512995"
print(f"Person-2f078c2e key present: {ALAN in seed}  -> {seed.get(ALAN)}")
json.dump(seed,open("alert_seed_list.json","w"),indent=1)
print(f"\nartifact written: alert_seed_list.json ({len(seed)} keys)")
