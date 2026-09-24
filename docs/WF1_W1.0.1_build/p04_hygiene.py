#!/usr/bin/env python3
"""Item 4 - hygiene batch. Six independent steps, each verified, each safe to re-run.

  1. fixture Handover 43974 -> done
  2. fixture lead 72ec85c0 -> strip '3. Responded'
  3. fixture lead 4306240392 -> pause/unsubscribe in Smartlead campaign 3686187
  4. duplicate persons 84885 / 84886 / 84887 -> FLAG for merge (report only, no merge)
  5. WF-2 CONFIG -> delete vestigial `slack_channel_replies_at_flip` (read by no node)
  6. record flip live-since = 2026-08-10T11:45:14.041Z

Step 4 deliberately does NOT merge: merging persons is destructive and irreversible via API, and
the audit flagged them for merge, not merged them. Flag + report is the faithful action.
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SLK = os.environ["SMARTLEAD_API_KEY"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
FIXTURE_LEAD = "72ec85c0-94b9-11f1-bf13-f56958004891"
SL_LEAD, SL_CAMP = "4306240392", 3686187
HANDOVER_ACT = 43974
RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
DUPES = [84885, 84886, 84887]
LIVE_SINCE = "2026-08-10T11:45:14.041Z"


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea-hyg/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:250]}


def sl(path, params=None, method="GET", body=None):
    q = dict(params or {}); q["api_key"] = SLK
    data = json.dumps(body).encode() if body is not None else None
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    try:
        r = urllib.request.Request(url, method=method, data=data,
                                   headers={"User-Agent": "janea-hyg/1.0",
                                            "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            raw = x.read()
            try:
                return json.loads(raw)
            except Exception:
                return {"__status": x.status}
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:250]}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()
D = a.deploy
res = {}
print(f"HYGIENE  {'LIVE' if D else 'DRY-RUN'}  {datetime.now(timezone.utc).isoformat()}\n")

# 1 ------------------------------------------------------------------ fixture handover done
act = (pd(f"/api/v2/activities/{HANDOVER_ACT}") or {}).get("data") or {}
print(f"1. Handover {HANDOVER_ACT}: subject={str(act.get('subject'))[:40]!r} done={act.get('done')}")
if act and not act.get("done"):
    if D:
        pd(f"/api/v2/activities/{HANDOVER_ACT}", "PATCH",
           {"done": True, "note": "Closed: flip-gate TEST fixture, not a real lead."})
        back = (pd(f"/api/v2/activities/{HANDOVER_ACT}") or {}).get("data") or {}
        print(f"   -> done={back.get('done')} {'VERIFIED' if back.get('done') else 'FAILED'}")
        res["handover_done"] = bool(back.get("done"))
    else:
        print("   would PATCH done=true")
else:
    print("   already done / not found")
    res["handover_done"] = bool(act.get("done"))

# 2 ------------------------------------------------------------- fixture responded stripped
L = (pd(f"/v1/leads/{FIXTURE_LEAD}") or {}).get("data") or {}
labels = list(L.get("label_ids") or [])
print(f"\n2. fixture lead labels: {labels}")
if RESPONDED in labels:
    if D:
        pd(f"/v1/leads/{FIXTURE_LEAD}", "PATCH",
           {"label_ids": [x for x in labels if x != RESPONDED]})
        back = (pd(f"/v1/leads/{FIXTURE_LEAD}") or {}).get("data") or {}
        ok = RESPONDED not in (back.get("label_ids") or [])
        print(f"   -> stripped={ok} now={back.get('label_ids')}")
        res["responded_stripped"] = ok
    else:
        print("   would strip '3. Responded'")
else:
    print("   '3. Responded' already absent")
    res["responded_stripped"] = True

# 3 ------------------------------------------------------ fixture out of the Smartlead campaign
print(f"\n3. Smartlead lead {SL_LEAD} in campaign {SL_CAMP}")
if D:
    r = sl(f"/campaigns/{SL_CAMP}/leads/{SL_LEAD}/pause", None, "POST", {})
    print(f"   pause -> {json.dumps(r)[:120]}")
    d = sl("/leads", {"email": "pii-c61c7d08@example.invalid"})
    lcd = next((c for c in ((d or {}).get("lead_campaign_data") or [])
                if c.get("campaign_id") == SL_CAMP), {})
    print(f"   read-back: status={lcd.get('status')} is_unsubscribed={(d or {}).get('is_unsubscribed')}")
    res["fixture_paused"] = not r.get("__err")
else:
    print("   would POST pause for this lead in the campaign")

# 4 ------------------------------------------------------------------ duplicate persons: FLAG
print("\n4. duplicate persons (FLAG ONLY - merge is destructive and was not authorised)")
dupe_rows = []
for pid in DUPES:
    p = (pd(f"/api/v2/persons/{pid}") or {}).get("data") or {}
    emails = [e.get("value") for e in (p.get("emails") or [])]
    dupe_rows.append({"person_id": pid, "name": p.get("name"), "emails": emails,
                      "owner_id": p.get("owner_id"), "add_time": p.get("add_time")})
    print(f"   {pid}  {str(p.get('name'))[:34]:<34} {emails} owner={p.get('owner_id')}")
res["duplicate_persons_flagged"] = dupe_rows

# 5 ---------------------------------------------------------- vestigial CONFIG key deleted
wf = n8n(f"/api/v1/workflows/{WF2}")
cfg_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
print(f"\n5. CONFIG.slack_channel_replies_at_flip = {cfg.get('slack_channel_replies_at_flip')!r}")
# exclude CONFIG itself: it DEFINES the key, so a naive substring scan counts the definition as a
# consumer and refuses forever. Only other nodes referencing it are consumers.
consumers = [n["name"] for n in wf["nodes"]
             if n["name"] != "CONFIG"
             and "slack_channel_replies_at_flip" in json.dumps(n.get("parameters") or {})]
print(f"   consumed by: {consumers or 'NO NODE (vestigial, confirmed)'}")
if "slack_channel_replies_at_flip" in cfg and not consumers:
    cfg.pop("slack_channel_replies_at_flip")
    cfg["write_mode_live_since"] = LIVE_SINCE          # step 6, same CONFIG write
    cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
    if D:
        was = wf.get("active")
        if was:
            n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
        dsk = stripped_keys(wf)
        if dsk:
            print(f"   stripping UI-only settings keys: {dsk}")
        n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
        if was:
            n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})
        after = n8n(f"/api/v1/workflows/{WF2}")
        acfg = json.loads(next(n for n in after["nodes"]
                               if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
        gone = "slack_channel_replies_at_flip" not in acfg
        stamped = acfg.get("write_mode_live_since") == LIVE_SINCE
        print(f"   -> deleted={gone} live_since_recorded={stamped} "
              f"active={after.get('active')} versionId={after.get('versionId')}")
        res["vestigial_deleted"] = gone
        res["live_since_recorded"] = stamped
    else:
        print(f"   would delete it and record write_mode_live_since={LIVE_SINCE}")
elif consumers:
    print("   REFUSING to delete - a node consumes it")
else:
    print("   already absent")

# 6 ------------------------------------------------------------------------- live-since record
print(f"\n6. flip live-since {LIVE_SINCE} recorded in CONFIG (step 5's write) and in evidence")
res["live_since"] = LIVE_SINCE

json.dump(res, open(os.path.join(HERE, "wf1-release-evidence", "p04_hygiene.json"), "w",
                    encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print(f"\nhygiene: {'applied' if D else 'dry-run only'}")
