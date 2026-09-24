#!/usr/bin/env python3
"""Person-9979a87c, 15:47, via Noah - alert said 'not in Pipedrive'.

Question: is person+lead creation for repliers automatic, or Slava's manual step? If automatic, why
did it not fire here? Find the execution FIRST - which workflow, which nodes ran, which gates said
no - rather than reasoning from the alert text.
"""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WFS = {"jp7rum9Z0YDJkQWv": "WF-2 Smartlead", "2jdjKM2NJr473GdA": "WF-1 HeyReach"}


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


hits = []
for wid, label in WFS.items():
    ex = (n8n(f"/api/v1/executions?workflowId={wid}&limit=40") or {}).get("data") or []
    for e in ex:
        d = n8n(f"/api/v1/executions/{e['id']}?includeData=true")
        rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if not rd:
            continue
        if "cootey" not in json.dumps(rd).lower():
            continue
        hits.append((label, e, rd, d))

print(f"executions mentioning Cootey: {len(hits)}\n")
for label, e, rd, d in hits:
    print(f"=== {label}  exec {e['id']}  {e.get('startedAt')}  status={e.get('status')} ===")

    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None

    nz = o("Normalize") or {}
    print(f"  event={nz.get('event')!r} campaign={str(nz.get('campaign_name'))[:44]!r}")
    print(f"  lead.email={(nz.get('lead') or {}).get('email')!r} "
          f"full_name={(nz.get('lead') or {}).get('full_name')!r}")
    print(f"  __reply_class={nz.get('__reply_class')!r} sender_inbox={nz.get('sender_inbox')!r}")
    err = ((d.get("data") or {}).get("resultData") or {}).get("error") or {}
    if err:
        print(f"  ERROR node={((err.get('node') or {}).get('name'))} "
              f"msg={str(err.get('message'))[:100]}")

    print("  --- the create path, node by node ---")
    for nm in ("R Person Search", "R Person Pick", "R Person Verify", "Body Person Create",
               "Gate Person Create", "Person Create", "Skip Person Create",
               "Lead Resolve", "R Lead List", "Body Lead Create", "Gate Lead Create",
               "Lead Create", "Skip Lead Create", "Body Lead Labels Union",
               "Gate Lead Labels Union", "Lead Labels Union", "Skip Lead Labels Union",
               "Body Reply Activity", "Gate Reply Activity", "Reply Activity",
               "Skip Reply Activity", "First Reply Gate", "Reply Alert"):
        if nm not in rd:
            continue
        j = o(nm) or {}
        bits = {k: j[k] for k in ("__skip", "__person_id", "__lead_id", "__should_alert",
                                 "__alert_reason", "__person_candidates", "id", "ok")
                if k in j}
        print(f"    {nm:<24} ran  {json.dumps(bits, ensure_ascii=False)[:88]}")
    absent = [nm for nm in ("Person Create", "Lead Create", "Reply Activity") if nm not in rd]
    print(f"    NEVER RAN: {absent}")
    print()

    em = (nz.get("lead") or {}).get("email")
    if em:
        s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&term={em}")
        items = ((s or {}).get("data") or {}).get("items") or []
        print(f"  Pipedrive now: person search for {em!r} -> {len(items)} hit(s)")
        for it in items[:3]:
            print(f"     person {(it.get('item') or {}).get('id')} "
                  f"{(it.get('item') or {}).get('name')!r}")
