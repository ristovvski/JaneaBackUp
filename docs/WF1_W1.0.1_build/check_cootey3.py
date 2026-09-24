#!/usr/bin/env python3
"""WF-1's reply path (M7) is RESOLVE-ONLY - Person Search / Person Get / Lead Get / Labels / Reply
Activity, with warns as the terminal branches. Create Lead + Lead Create Gate live on the earlier
invite/sent path.

So for a replier to be in the CRM, the EARLIER contact event must have created them. Person-9979a87c
is an InMail (is_inmail: true) with no email of any kind. Two questions:
  1. does he exist in Pipedrive at all (by name / by LinkedIn URL), i.e. did we just fail to MATCH?
  2. did WF-1 ever see an earlier event for him - or does the InMail path never create anyone,
     making every InMail replier permanently 'not in Pipedrive'?
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


print("=== 1. is Person-9979a87c in Pipedrive under ANY key? ===")
for label, term in (("name", "Person-9979a87c"), ("linkedin slug", "philipcootey"),
                    ("company", "Babel Street")):
    r = pd(f"/api/v2/persons/search?limit=5&term={urllib.parse.quote(term)}")
    items = ((r or {}).get("data") or {}).get("items") or []
    print(f"  search by {label:<14} {term!r} -> {len(items)} hit(s)")
    for it in items[:3]:
        p = it.get("item") or {}
        print(f"     person {p.get('id')} {p.get('name')!r}")

print("\n=== 2. every WF-1 event we have retained for this lead / conversation ===")
ex = (n8n("/api/v1/executions?workflowId=2jdjKM2NJr473GdA&limit=120") or {}).get("data") or []
print(f"  scanning {len(ex)} retained WF-1 executions")
inmail_reply = []
seen_lead = []
for e in ex:
    d = n8n(f"/api/v1/executions/{e['id']}?includeData=true")
    rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
    if not rd:
        continue
    try:
        nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    lead = nz.get("lead") or {}
    if str(lead.get("id")) == "10891837" or "philipcootey" in str(lead.get("slug") or ""):
        seen_lead.append((e["id"], e.get("startedAt"), nz.get("event"), list(rd.keys())))
    ev = str(nz.get("event") or "")
    if "reply" in ev.lower():
        em = lead.get("email_address") or lead.get("enriched_email") or lead.get("custom_email")
        inmail_reply.append({
            "id": e["id"], "at": e.get("startedAt"), "inmail": nz.get("is_inmail"),
            "has_email": bool(em), "name": lead.get("full_name"),
            "warned": "M7 Slack Warn" in rd, "no_lead_warn": "M7 No Lead Warn" in rd,
            "activity": "M7 Reply Activity" in rd, "patched": "M7 Lead Patch" in rd})

print(f"\n  events for THIS lead: {len(seen_lead)}")
for i, at, ev, nodes in seen_lead:
    print(f"     exec {i} {at} event={ev!r} nodes={len(nodes)}")

print(f"\n=== 3. all retained WF-1 reply events: does InMail predict 'not in Pipedrive'? ===")
print(f"  reply events retained: {len(inmail_reply)}")
im = [r for r in inmail_reply if r["inmail"]]
non = [r for r in inmail_reply if not r["inmail"]]
for label, grp in (("InMail", im), ("connected/other", non)):
    if not grp:
        print(f"  {label:<16} 0")
        continue
    print(f"  {label:<16} {len(grp):<3} "
          f"with any email: {sum(1 for r in grp if r['has_email'])}  "
          f"person-unresolved warn: {sum(1 for r in grp if r['warned'])}  "
          f"no-lead warn: {sum(1 for r in grp if r['no_lead_warn'])}  "
          f"reply activity written: {sum(1 for r in grp if r['activity'])}")
print("\n  per-event detail:")
for r in sorted(inmail_reply, key=lambda x: str(x["at"]), reverse=True)[:14]:
    print(f"     {r['at']}  {str(r['name'])[:22]:<22} inmail={str(r['inmail']):<5} "
          f"email={str(r['has_email']):<5} warn={str(r['warned']):<5} "
          f"noLead={str(r['no_lead_warn']):<5} activity={r['activity']}")
