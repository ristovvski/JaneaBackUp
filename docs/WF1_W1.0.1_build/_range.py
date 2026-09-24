import json,os,ssl,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
for wid,label in (("jp7rum9Z0YDJkQWv","WF-2"),("2jdjKM2NJr473GdA","WF-1")):
    d=(n8n(f"/api/v1/executions?workflowId={wid}&limit=250") or {})
    rows=d.get("data") or []
    ts=sorted([r.get("startedAt") for r in rows if r.get("startedAt")])
    print(f"{label}: {len(rows)} retained, oldest={ts[0] if ts else '?'} newest={ts[-1] if ts else '?'} nextCursor={'yes' if d.get('nextCursor') else 'no'}")
    # count per day
    from collections import Counter
    c=Counter(t[:10] for t in ts)
    print("   per day:", dict(sorted(c.items())))
