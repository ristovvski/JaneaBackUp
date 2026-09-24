import json,os,ssl,urllib.parse,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
FRAG="f6bfaf70"
def walk(wid,label,want_days):
    cur=None; seen=0; pages=0; found=[]
    while pages<12:
        q={"workflowId":wid,"limit":250}
        if cur: q["cursor"]=cur
        d=n8n("/api/v1/executions?"+urllib.parse.urlencode(q)) or {}
        rows=d.get("data") or []
        if not rows: break
        for r in rows:
            seen+=1
            day=str(r.get("startedAt") or "")[:10]
            if day not in want_days: continue
            det=n8n(f"/api/v1/executions/{r['id']}?includeData=true")
            rd=((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
            if not rd: continue
            if FRAG not in json.dumps(rd): continue
            found.append((r,rd))
        cur=d.get("nextCursor"); pages+=1
        if not cur: break
    print(f"{label}: walked {seen} executions over {pages} page(s); matches in {sorted(want_days)}: {len(found)}")
    return found
DAYS={"2026-08-16","2026-08-17","2026-08-18"}
for wid,label in (("2jdjKM2NJr473GdA","WF-1"),):
    for r,rd in walk(wid,label,DAYS):
        def o(nm):
            try: return rd[nm][0]["data"]["main"][0][0]["json"]
            except Exception: return None
        nz=o("Normalize") or {}
        g=o("First Reply Gate") or o("M7 Alert Gate") or {}
        al=o("Reply Alert") or o("M7 Critical Slack") or {}
        print(f"  exec {r['id']} {r.get('startedAt')} status={r.get('status')}")
        print(f"     event={nz.get('event')!r} lead={(nz.get('lead') or {}).get('email') or (nz.get('lead') or {}).get('full_name')!r}")
        print(f"     gate should={g.get('__should_alert')} reason={g.get('__alert_reason')!r} regsize={g.get('__alert_registry_size')}")
        print(f"     key={g.get('__alert_key')!r}")
        print(f"     alert ok={al.get('ok')} chan={al.get('channel')}")
        print(f"     nodes={len(rd)}")
