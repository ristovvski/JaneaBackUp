import json,os,re,ssl,urllib.parse,urllib.request
BASE=os.environ["N8N_BASE_URL"].rstrip("/"); KEY=os.environ["N8N_API_KEY"]
CA=os.environ.get("REQUESTS_CA_BUNDLE"); ctx=ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
def n8n(p,a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+p,headers={"X-N8N-API-KEY":KEY}),timeout=300,context=ctx) as x: return json.load(x)
    except Exception:
        if a<4: time.sleep(6); return n8n(p,a+1)
        raise
cur=None; wfs=[]
while True:
    q={"limit":250}
    if cur: q["cursor"]=cur
    d=n8n("/api/v1/workflows?"+urllib.parse.urlencode(q)) or {}
    wfs+=d.get("data") or []
    cur=d.get("nextCursor")
    if not cur: break
print(f"workflows in estate: {len(wfs)}")
PATTERNS={
 "event_contacted":re.compile(r"event_contacted"),
 "S4":re.compile(r"\bS4\b"),
 "Events Visiting literal":re.compile(r"Events Visiting"),
 "campaign id 3686/512/513":re.compile(r"368618[0-9]|3686193|512995|513000"),
 "campaign_name regex/match":re.compile(r"campaign_name[^\n]{0,60}(match|indexOf|includes|startsWith|test\()"),
 "bracket parser":re.compile(r"\\[([^\\]]+)\\]|\[\s\*\(\[\^\\]\]"),
 "event_campaign_ids CONFIG":re.compile(r"event_campaign|campaign_ids|event_ids|eventCampaigns"),
}
hits={k:[] for k in PATTERNS}
for w in wfs:
    full=n8n(f"/api/v1/workflows/{w['id']}")
    blob=json.dumps(full,ensure_ascii=False)
    for k,rx in PATTERNS.items():
        if rx.search(blob): hits[k].append((w["id"],w["name"],full.get("active")))
for k,v in hits.items():
    print(f"\n### {k}: {len(v)} workflow(s)")
    for wid,nm,act in v[:12]: print(f"    {wid}  {'ACTIVE' if act else 'inact '}  {nm[:60]}")
