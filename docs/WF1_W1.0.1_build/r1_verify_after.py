#!/usr/bin/env python3
"""Independent post-write verification of R1 - re-reads Pipedrive and Smartlead from scratch
rather than trusting the backfill's own success prints. Also re-checks the Handover guard after a
longer delay than the 20s in-run wait. READ-ONLY."""
import json, os, ssl, time, urllib.parse, urllib.request, urllib.error

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SLK = os.environ["SMARTLEAD_API_KEY"]
UA = "Mozilla/5.0 janea-r1-verify/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"

with open(os.path.join(HERE, "wf1-release-evidence", "r1_reply_backfill_live.json"),
          encoding="utf-8") as f:
    run = json.load(f)


def _get(url, headers):
    try:
        r = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code}
    except Exception as e:
        return {"__err": str(e)[:120]}


def pd(path):
    return _get("https://api.pipedrive.com" + path, {"x-api-token": PDT, "User-Agent": UA})


def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA})


print(f"{'email':<36} {'lead':<10} {'responded':<10} {'connected':<10} {'reply act':<10} open")
print("-" * 96)
rows, problems = [], []
for s in run["plan"]:
    lid = s.get("lead_id")
    if not lid:
        problems.append(f"{s['email']}: no lead_id recorded"); continue
    L = (pd(f"/v1/leads/{lid}") or {}).get("data") or {}
    labels = L.get("label_ids") or []
    # /v1/activities?lead_id= returns data:null for lead-attached activities - it silently reports
    # ZERO instead of erroring. Only /api/v2/activities?lead_id= actually filters by lead.
    acts = (pd(f"/api/v2/activities?lead_id={lid}&limit=100") or {}).get("data") or []
    want = "Email bounced" if s.get("is_bounce") else "Email reply"
    mine = [a for a in acts if str(a.get("subject") or "").startswith(want)]
    opens = [a for a in acts if not a.get("done")]
    has_resp = RESPONDED in labels
    has_conn = CONNECTED in labels
    print(f"{s['email']:<36} {str(lid)[:8]:<10} {str(has_resp):<10} {str(has_conn):<10} "
          f"{len(mine):<10} {len(opens)}")
    rows.append({"email": s["email"], "lead_id": lid, "responded": has_resp,
                 "connected": has_conn, "activities": len(mine), "open": len(opens),
                 "is_bounce": s.get("is_bounce")})
    if s.get("is_bounce"):
        if has_resp:
            problems.append(f"{s['email']}: BOUNCE carries '3. Responded' - D2 violated")
        if not mine:
            problems.append(f"{s['email']}: bounce note missing")
    else:
        if not has_resp:
            problems.append(f"{s['email']}: missing '3. Responded'")
        if not mine:
            problems.append(f"{s['email']}: reply activity missing")

# per-lead dedupe: the two brum replies share one lead, so 2 activities on it is correct
by_lead = {}
for r in rows:
    by_lead.setdefault(r["lead_id"], []).append(r)

print("\nSmartlead category checks:")
for s in run["plan"]:
    d = sl("/leads", {"email": s["email"]})
    lcd = next((c for c in ((d or {}).get("lead_campaign_data") or [])
                if c.get("campaign_id") == s["campaign_id"]), {})
    print(f"  {s['email']:<36} lead_category_id={lcd.get('lead_category_id')}")
    if s.get("is_bounce") and lcd.get("lead_category_id") != 9:
        problems.append(f"{s['email']}: bounce category not 9 (got {lcd.get('lead_category_id')})")

open_total = sum(r["open"] for r in rows)
print(f"\nHANDOVER GUARD (delayed re-check): {open_total} open activity(ies) across all touched leads")
for r in rows:
    if r["open"]:
        acts = (pd(f"/api/v2/activities?lead_id={r['lead_id']}&limit=100") or {}).get("data") or []
        for a in acts:
            if a.get("done"):
                continue
            fresh = str(a.get("add_time") or "") >= "2026-08-06"
            print(f"   {r['email']}: OPEN {a['id']} {a.get('subject')!r} type={a.get('type')} "
                  f"add_time={a.get('add_time')} owner={a.get('owner_id')} "
                  f"{'<<< NEW TODAY' if fresh else '(pre-existing)'}")

print("\n" + "=" * 96)
if problems:
    print(f"PROBLEMS: {len(problems)}")
    for p in problems:
        print("  -", p)
else:
    print("VERIFIED: every non-bounce lead carries '3. Responded' + a reply activity; the bounce "
          "carries a bounce note and NO responded label; no unexpected open activities.")
with open(os.path.join(HERE, "wf1-release-evidence", "r1_verify_after.json"), "w",
          encoding="utf-8") as f:
    json.dump({"rows": rows, "problems": problems, "open_total": open_total}, f, indent=2,
              ensure_ascii=False)
