#!/usr/bin/env python3
"""The resolver MATCHED Ken (items=1, PID From URL / Person Get / Lead Get / Lead Patch all ran).
So "match miss" is not what happened. Read the posted alert text and the lead's real history before
proposing any fix."""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


d = n8n("/api/v1/executions/33785?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}


def o(nm):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception:
        return None


print("=" * 78)
print("WHAT WAS ACTUALLY POSTED (exec 33785)")
print("=" * 78)
cs = o("M7 Critical Slack") or {}
txt = ((cs.get("message") or {}).get("text")) or ""
print(f"channel: {cs.get('channel')}   ok={cs.get('ok')}")
print("-" * 60)
print(txt[:900])
print("-" * 60)

print("\nresolver chain, values:")
for nm in ("M7 Person Search URL", "M7 PID From URL", "M7 Person Get", "M7 Lead Get",
           "M7 Labels Compute", "M7 Build", "M7 Alert Gate"):
    j = o(nm)
    if j is None:
        print(f"   {nm:<24} did not run")
        continue
    if nm == "M7 Person Search URL":
        items = ((j.get("data") or {}) or {}).get("items") or []
        print(f"   {nm:<24} items={len(items)} -> "
              f"{[(i.get('item') or {}).get('id') for i in items]}")
    elif nm == "M7 Labels Compute":
        print(f"   {nm:<24} lead_id={j.get('lead_id')} person_id={j.get('person_id')} "
              f"changed={j.get('changed')} before={len(j.get('label_ids_before') or [])} "
              f"after={len(j.get('label_ids') or [])}")
    elif nm == "M7 Alert Gate":
        print(f"   {nm:<24} should_alert={j.get('__should_alert')} "
              f"reason={j.get('__alert_reason')!r} key={str(j.get('__alert_key'))[:40]!r}")
    else:
        keys = [k for k in j if not k.startswith("data")][:5]
        print(f"   {nm:<24} {json.dumps({k: j[k] for k in keys}, ensure_ascii=False)[:90]}")

print("\n" + "=" * 78)
print("LEAD HISTORY — was the lead new, or pre-existing?")
print("=" * 78)
l = (pd("/v1/leads/a8fca300-9682-11f1-b6d6-19031bcb002c") or {}).get("data") or {}
print(f"  title={l.get('title')!r}")
print(f"  add_time={l.get('add_time')}   update_time={l.get('update_time')}")
print(f"  creator={l.get('creator_id')} owner={l.get('owner_id')} person={l.get('person_id')}")
names = {str(x.get("id")): x.get("name")
         for x in ((pd("/v1/leadLabels") or {}).get("data") or [])}
print(f"  labels: {[(x, names.get(x)) for x in (l.get('label_ids') or [])]}")
acts = (pd("/api/v2/activities?lead_id=a8fca300-9682-11f1-b6d6-19031bcb002c&limit=50")
        or {}).get("data") or []
print(f"  activities: {len(acts)}")
for a in acts:
    print(f"     {a.get('id')} {str(a.get('subject'))[:50]!r} due={a.get('due_date')}")
