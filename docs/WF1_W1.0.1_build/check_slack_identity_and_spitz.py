#!/usr/bin/env python3
"""Two answers before repointing anything.

A. ONE APP OR TWO? Nik added a "Heyreach"-named app card to #gtm-telemetry. If the Smartlead-named
   nodes post through a DIFFERENT credential, repointing them lands not_in_channel. The n8n node
   carries its credential id/name, so this is a read, not a guess - and a test-post from MY side
   would use Nik's user token and prove nothing about the app identity the NODES use.

B. richard.spitz - his SENT event crashed in the 19:01 worker death. Confirm it is queued for
   WF-2S's next replay: unclaimed in WF-2's wf2_seen AND absent from WF-2S's __sent_seen_v2.
   Per section 9b.0e both halves must be true, or he is stranded like tonight's 32.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2, WF2S = "jp7rum9Z0YDJkQWv", "6Y92ryBwYoy6z0Jx"


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=150, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"   read failed: {str(e)[:110]}")
        return None


def ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


print("A. WHICH SLACK CREDENTIAL DOES EACH POSTING NODE USE?")
rows, cursor = [], None
while True:
    q = {"limit": 100}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/workflows", q)
    rows += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor:
        break
creds = Counter()
per_wf = {}
for w in rows:
    wf = n8n(f"/api/v1/workflows/{w['id']}")
    slack = [n for n in (wf or {}).get("nodes", []) if n["type"].endswith("slack")]
    if not slack:
        continue
    got = []
    for n in slack:
        c = (n.get("credentials") or {}).get("slackApi") or {}
        key = f"{c.get('name')} ({c.get('id')})"
        creds[key] += 1
        got.append((n["name"], key))
    per_wf[w["name"]] = got
for k, v in creds.most_common():
    print(f"   {k:<46} {v} nodes")
print(f"\n   DISTINCT Slack credentials in the estate: {len(creds)}")
if len(creds) == 1:
    print("   => ONE app identity. Whatever Nik added covers every posting node.")
else:
    print("   => MORE THAN ONE. Repointing is only safe for nodes on the invited app:")
    for wfn, got in per_wf.items():
        for nm, key in got:
            print(f"      {wfn[:26]:<28} {nm:<26} {key}")

print("\nB. richard.spitz - queued for replay, or stranded?")
w2 = n8n(f"/api/v1/workflows/{WF2}")
ws = n8n(f"/api/v1/workflows/{WF2S}")
wseen = ((w2 or {}).get("staticData") or {}).get("global", {}).get("wf2_seen") or {}
sseen = ((ws or {}).get("staticData") or {}).get("global", {}).get("__sent_seen_v2") or {}
print(f"   wf2_seen={len(wseen)}  __sent_seen_v2={len(sseen)}")

found = []
ids, cursor = [], None
while True:
    q = {"workflowId": WF2, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    ids += (p or {}).get("data") or []
    cursor = (p or {}).get("nextCursor")
    if not cursor or len(ids) > 400:
        break
for e in ids:
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        nm = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    em = str((nm.get("lead") or {}).get("email") or "").lower()
    if "spitz" not in em:
        continue
    ded = {}
    try:
        ded = rd["Dedupe"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    wh = {}
    try:
        wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
    except Exception:
        pass
    body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
    sid = (body or {}).get("stats_id")
    dk = ded.get("__dedupe_key")
    found.append({"exec": e["id"], "at": e.get("startedAt"), "status": e.get("status"),
                  "email": em, "event": nm.get("event"), "key": dk, "stats_id": sid,
                  "claimed": dk in wseen if dk else None,
                  "wf2s_blocked": sid in sseen if sid else None})
print(f"   executions found for spitz: {len(found)}")
for f in found:
    print(f"      exec {f['exec']} {f['at']} status={f['status']} event={f['event']}")
    print(f"         dedupe_key claimed in WF-2 : {f['claimed']}   (False = outstanding, good)")
    print(f"         stats_id blocked in WF-2S  : {f['wf2s_blocked']}  (True = WF-2S will NOT retry)")
    if f["claimed"] is False and f["wf2s_blocked"] is True:
        print("         *** STRANDED - same shape as tonight's 32; needs a WF-2S key release")
    elif f["claimed"] is False and f["wf2s_blocked"] is False:
        print("         OK - outstanding in WF-2 and visible to WF-2S: it will replay")
    elif f["claimed"] is True:
        print("         already processed - nothing owed")
