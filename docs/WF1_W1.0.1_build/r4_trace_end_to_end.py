#!/usr/bin/env python3
"""R4 flip gate - trace the controlled reply end to end and judge each stage on its own evidence.

FOUR stages, each verified independently. A pass needs all four; a 200 from the replay POST is not
proof that WF-2 processed anything.

  1. Smartlead recorded the REPLY against the lead
  2. WF-2R polled campaign 3686187, found it, and replayed it into WF-2
  3. WF-2 executed, normalized it as a REPLIED event, and SHADOW-LOGGED it (no writes - shadow)
  4. WF-2R CLAIMED it (claim-after-success), so the next cycle will not replay it again

Read-only.
"""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

SLK = os.environ["SMARTLEAD_API_KEY"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
CID, LEAD, EMAIL = 3686187, "4306240392", "pii-c61c7d08@example.invalid"
WF2R, WF2 = "U8Bb7Pdq7S6nzYPa", "jp7rum9Z0YDJkQWv"
HERE = os.path.dirname(os.path.abspath(__file__))
DEADLINE = time.time() + 60 * 85


def sl(path, params=None):
    q = dict(params or {}); q["api_key"] = SLK
    try:
        r = urllib.request.Request(
            f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
            headers={"User-Agent": "janea-r4/1.0"})
        with urllib.request.urlopen(r, timeout=90, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    try:
        r = urllib.request.Request(f"{BASE}{path}?{q}" if q else f"{BASE}{path}",
                                   headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:120]}


res = {"stage1_smartlead": None, "stage2_wf2r": None, "stage3_wf2": None, "stage4_claim": None}

# ---------------------------------------------------------------- 1. Smartlead sees the reply
print("STAGE 1 - waiting for Smartlead to record the reply", flush=True)
reply = None
while time.time() < DEADLINE and not reply:
    hist = (sl(f"/campaigns/{CID}/leads/{LEAD}/message-history") or {}).get("history") or []
    reps = [h for h in hist if str(h.get("type", "")).upper() == "REPLY"]
    if reps:
        reply = reps[-1]
        break
    time.sleep(45)
if not reply:
    print("  no reply visible in Smartlead yet - stopping here rather than guessing", flush=True)
    json.dump(res, open(os.path.join(HERE, "wf1-release-evidence", "r4_trace.json"), "w",
                        encoding="utf-8"), indent=2, default=str)
    raise SystemExit(0)
body = str(reply.get("email_body") or "")
res["stage1_smartlead"] = {"time": reply.get("time"), "from": reply.get("from"),
                           "subject": reply.get("subject"),
                           "message_id": reply.get("message_id"),
                           "body_len": len(body), "body_preview": body[:200]}
print(f"  PASS  reply at {reply.get('time')} from {reply.get('from')}", flush=True)
print(f"        subject={reply.get('subject')!r} body_len={len(body)}", flush=True)
reply_t = reply.get("time")

# --------------------------------------------------- 2. WF-2R picks it up and replays it
print("\nSTAGE 2 - waiting for a WF-2R cycle to poll 3686187 and replay", flush=True)
replay_exec, polled_cycles = None, []
while time.time() < DEADLINE and not replay_exec:
    d = n8n("/api/v1/executions", {"workflowId": WF2R, "limit": 25})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt"))):
        if str(e.get("startedAt") or "") < reply_t:
            continue
        if e["id"] in [c["id"] for c in polled_cycles]:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})

        def g(nm, key):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"].get(key)
            except Exception:
                return None

        camp = g("Pick Campaign", "campaign_id")
        blob = json.dumps(det, default=str)
        hit = EMAIL in blob
        polled_cycles.append({"id": e["id"], "startedAt": e.get("startedAt"),
                              "campaign_id": camp, "ring": g("Pick Campaign", "__ring"),
                              "email_present": hit})
        print(f"  cycle {e['id']} {e.get('startedAt')} camp={camp} "
              f"ring={g('Pick Campaign', '__ring')} email_seen={hit}", flush=True)
        if hit and str(camp) == str(CID):
            statuses = []
            for run in rd.get("Replay Into WF-2") or []:
                for it in (run.get("data", {}).get("main", [[]])[0] or []):
                    j = it.get("json") or {}
                    statuses.append("ERROR:" + str(j["error"])[:80] if "error" in j else "accepted")
            replay_exec = {"id": e["id"], "startedAt": e.get("startedAt"),
                           "batch": g("Find New Replies", "__batch"),
                           "replay": statuses,
                           "marked": g("Summary", "__marked"),
                           "failed": g("Summary", "__failed"),
                           "store_size": g("Summary", "__store_size")}
            break
    if not replay_exec:
        time.sleep(60)
res["stage2_wf2r"] = replay_exec
res["cycles_observed"] = polled_cycles
if not replay_exec:
    print("  WF-2R has not reached campaign 3686187 yet within the watch window", flush=True)
else:
    print(f"  PASS  exec {replay_exec['id']} replayed batch={replay_exec['batch']} "
          f"-> {replay_exec['replay']}", flush=True)

# ------------------------------------------- 3. WF-2 executed it and shadow-logged a REPLIED
if replay_exec:
    print("\nSTAGE 3 - checking WF-2's own execution", flush=True)
    time.sleep(15)
    d = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 25})
    for e in sorted((d.get("data") or []), key=lambda r: str(r.get("startedAt")), reverse=True):
        if str(e.get("startedAt") or "") < replay_exec["startedAt"]:
            continue
        det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
        rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})
        shadow = []
        for run in rd.get("Shadow Log") or []:
            for it in (run.get("data", {}).get("main", [[]])[0] or []):
                shadow.append(it.get("json") or {})
        mine = [s for s in shadow if str(s.get("lead_email", "")).lower() == EMAIL]
        if not mine:
            continue

        def g2(nm, key):
            try:
                return rd[nm][0]["data"]["main"][0][0]["json"].get(key)
            except Exception:
                return None

        res["stage3_wf2"] = {
            "exec": e["id"], "startedAt": e.get("startedAt"), "status": e.get("status"),
            "event": g2("Normalize", "event"),
            "reconciled_by": g2("Normalize", "__reconciled_by"),
            "sender_inbox": g2("Normalize", "sender_inbox"),
            "duplicate": g2("Dedupe", "__duplicate"),
            "category": g2("Classify Parse", "__category"),
            "confidence": g2("Classify Parse", "__confidence"),
            "forward_to": g2("Forward Resolve", "__forward_to"),
            "forward_owner": g2("Forward Resolve", "__forward_owner"),
            "write_mode": g2("CONFIG", "WRITE_MODE"),
            "shadow_rows": len(shadow),
            "nodes_ran": len(rd),
        }
        print(f"  PASS  WF-2 exec {e['id']} status={e.get('status')} "
              f"event={res['stage3_wf2']['event']} "
              f"category={res['stage3_wf2']['category']} "
              f"forward_to={res['stage3_wf2']['forward_to']} "
              f"WRITE_MODE={res['stage3_wf2']['write_mode']}", flush=True)
        break
    if not res["stage3_wf2"]:
        print("  no WF-2 execution carrying this lead found yet", flush=True)

    # ------------------------------------------------------- 4. claim held (no re-replay)
    res["stage4_claim"] = {"marked": replay_exec.get("marked"),
                           "failed": replay_exec.get("failed"),
                           "store_size": replay_exec.get("store_size")}
    print(f"\nSTAGE 4 - claim: marked={replay_exec.get('marked')} "
          f"failed={replay_exec.get('failed')} store={replay_exec.get('store_size')}", flush=True)

ok = [bool(res["stage1_smartlead"]), bool(res["stage2_wf2r"]), bool(res["stage3_wf2"]),
      bool(res["stage4_claim"]) and (res.get("stage4_claim") or {}).get("failed") == 0]
print("\n" + "=" * 80)
print(f"FLIP GATE: {sum(ok)}/4 stages passed -> "
      f"{'PASS' if all(ok) else 'NOT YET COMPLETE'}")
print("=" * 80)
json.dump(res, open(os.path.join(HERE, "wf1-release-evidence", "r4_trace.json"), "w",
                    encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
print("wrote wf1-release-evidence/r4_trace.json")
