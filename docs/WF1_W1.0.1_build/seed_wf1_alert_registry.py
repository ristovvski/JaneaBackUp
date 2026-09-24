#!/usr/bin/env python3
"""Build the WF-1 alert-registry seed from DELIVERY EVIDENCE. Read-only walk; writes a JSON plan.

Nik's rule: "first alert" = first DELIVERED TO THE TEAM CHANNEL (C07LTD8UT70). An alert that went
only to ops, failed, or was suppressed was not an alert, and that lead gets one real alert on its
next reply.

TWO PREMISES IN THE BRIEF ARE WRONG FOR WF-1, and they change the outcome:

  1. WF-1's CONFIG already has slack_channel_replies = C07LTD8UT70. `M7 Critical Slack` has been
     posting to the TEAM channel all along - the "everything went to ops before the switch" premise
     is true of WF-2, not WF-1. So WF-1's seed set is potentially LARGE, and the corollary claim
     that the next reply produces "#lead-processing's FIRST EVER message" is false for WF-1.
  2. WF-1's __alerted_v1 already holds 50 entries, written by the OLD gate at DECISION time
     (`reg[key] = ...` before the post). Those are exactly the claims Nik's rule rejects: a lead
     whose post then failed is muted forever on evidence that proves nothing. So the registry is
     REBUILT from delivery evidence, not merged into - merging would preserve the bad claims.

Classification per execution, from the wire (Slack's own response), never from "the node ran":
  delivered_team : M7 Critical Slack ok === true AND channel === C07LTD8UT70   -> SEED (muted)
  delivered_ops  : ok === true but a different channel                         -> NOT seeded
  post_failed    : node ran, ok !== true                                       -> NOT seeded
  suppressed     : gate said don't alert                                       -> NOT seeded
  unclassified   : no gate/alert data (predates the nodes)                     -> COUNTED, not guessed
"""
import json, os, ssl, sys, urllib.parse, urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"
TEAM = "C07LTD8UT70"
OUT = os.path.join(HERE, "wf1-release-evidence", "wf1_registry_seed.json")


def n8n(p, q=None):
    url = BASE + p + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        print(f"  read FAILED (not an empty result): {str(e)[:120]}", flush=True)
        return None


def nd(rd, nm, k):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"].get(k)
    except Exception:
        return None


ids, cursor = [], None
while True:
    q = {"workflowId": WF1, "limit": 250}
    if cursor:
        q["cursor"] = cursor
    p = n8n("/api/v1/executions", q)
    if not p:
        sys.exit("execution list read failed - refusing to seed from a partial walk")
    ids += [(e["id"], e.get("startedAt"), e.get("status")) for e in (p.get("data") or [])]
    cursor = p.get("nextCursor")
    if not cursor:
        break
print(f"WF-1 executions to inspect: {len(ids)}", flush=True)

seed, detail, kinds, unread = {}, [], Counter(), 0
for i, (eid, started, status) in enumerate(ids, 1):
    if i % 100 == 0:
        print(f"  ...{i}/{len(ids)}  seeded so far: {len(seed)}", flush=True)
    det = n8n(f"/api/v1/executions/{eid}", {"includeData": "true"})
    if det is None:
        unread += 1                      # counted, never silently treated as "nothing here"
        continue
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
    key = nd(rd, "M7 Alert Gate", "__alert_key")
    ran_alert = "M7 Critical Slack" in rd
    ok = nd(rd, "M7 Critical Slack", "ok")
    ch = nd(rd, "M7 Critical Slack", "channel")
    if ch is None and ran_alert:
        try:
            msg = rd["M7 Critical Slack"][0]["data"]["main"][0][0]["json"]
            ch = ch or msg.get("channel") or (msg.get("message") or {}).get("channel")
        except Exception:
            pass
    should = nd(rd, "M7 Alert Gate", "__should_alert")

    if not ran_alert and should is None:
        kinds["unclassified_no_alert_nodes"] += 1
        continue
    if ran_alert and ok is True and ch == TEAM:
        kind = "delivered_team"
        if key:
            seed[key] = started
    elif ran_alert and ok is True:
        kind = "delivered_ops_or_other"
    elif ran_alert:
        kind = "post_failed"
    elif should is False:
        kind = "suppressed"
    else:
        kind = "no_post_no_suppression"
    kinds[kind] += 1
    if kind != "delivered_team":
        detail.append({"exec": eid, "at": started, "kind": kind, "key": key,
                       "channel": ch, "ok": ok, "status": status,
                       "who": nd(rd, "Normalize", "lead") or nd(rd, "M7 Build", "lead_id"),
                       "reason": nd(rd, "M7 Alert Gate", "__alert_reason")})

print("\n--- classification (coverage printed, nothing inferred) ---")
for k, v in kinds.most_common():
    print(f"  {k:<28} {v}")
print(f"  {'executions unreadable':<28} {unread}")
print(f"\nSEED (delivered to {TEAM}, ok:true): {len(seed)} unique alert keys")

live = n8n(f"/api/v1/workflows/{WF1}")
cur = ((live.get("staticData") or {}).get("global") or {}).get("__alerted_v1") or {}
print(f"current __alerted_v1 (claimed at DECISION time by the old gate): {len(cur)}")
would_unmute = [k for k in cur if k not in seed]
print(f"  -> entries the rebuild REMOVES (never proven delivered to team): {len(would_unmute)}")
print(f"  -> entries retained: {len(cur) - len(would_unmute)}")
print(f"  -> keys the rebuild ADDS (delivered, but not in the old registry): "
      f"{len([k for k in seed if k not in cur])}")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"seed": seed, "counts": dict(kinds), "unreadable": unread,
               "current_registry": cur, "removes": would_unmute,
               "not_seeded_detail": detail[:400]}, f, indent=2, ensure_ascii=False, default=str)
print(f"\nplan written: {OUT}")
print("NOTHING WRITTEN to the workflow - seeding is a separate, gated step.")
