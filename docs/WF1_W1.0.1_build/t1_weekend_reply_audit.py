#!/usr/bin/env python3
"""TASK 1 - weekend HeyReach replies vs WF-1 processing vs Slack notification.

Ground truth is HeyReach's OWN inbox (/inbox/GetConversationsV2), not our executions - the whole
point is to find replies our side may not know about. For every inbound message in the window:

  * did a WF-1 execution fire?
  * were CRM writes made (labels / reply activity)?
  * was an alert POSTED, or suppressed - and if suppressed, on what reason?
  * where would that alert have gone?

The hypothesis under test is that everything processed and only the CHANNEL was wrong. A
suppressed alert would NOT be a channel problem, so the two are reported separately rather than
collapsed into one verdict.

READ-ONLY. No writes, no Slack posts.
"""
import json, os, ssl, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timezone

HRK = os.environ["HEYREACH_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"
HERE = os.path.dirname(os.path.abspath(__file__))

# Saturday 00:00Z through now (Monday). Per-reply timestamps are printed so a timezone argument
# about "the weekend" can be settled from the evidence rather than from the window choice.
SINCE = os.environ.get("SINCE", "2026-08-08T00:00:00Z")
SINCE_DT = datetime.fromisoformat(SINCE.replace("Z", "+00:00"))
NOW = datetime.now(timezone.utc)


def _req(url, headers, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers, method=method, data=data)
            with urllib.request.urlopen(r, timeout=150, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:150]}
    return {}


def hr(path, body):
    return _req("https://api.heyreach.io/api/public" + path,
                {"X-API-KEY": HRK, "Accept": "application/json",
                 "Content-Type": "application/json"}, "POST", body)


def pd(path):
    return _req("https://api.pipedrive.com" + path,
                {"x-api-token": PDT, "User-Agent": "janea-t1/1.0"})


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    return _req(f"{BASE}{path}?{q}" if q else f"{BASE}{path}",
                {"X-N8N-API-KEY": KEY, "accept": "application/json"})


def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def slug(u):
    s = str(u or "").split("?")[0].rstrip("/")
    return s.split("/in/")[-1].lower() if "/in/" in s else s.lower()


print(f"window: {SINCE} .. {NOW.isoformat()}\n")

# ------------------------------------------------------- 1. HeyReach inbox = ground truth
convs, offset, truncated = [], 0, []
while offset < 2000:
    d = hr("/inbox/GetConversationsV2", {"filters": {}, "offset": offset, "limit": 100})
    if d.get("__err"):
        print("inbox error:", d); break
    items = d.get("items") or []
    convs.extend(items)
    offset += len(items)
    if len(items) < 100 or offset >= int(d.get("totalCount") or 0):
        break
    time.sleep(0.2)
print(f"conversations pulled: {len(convs)}")

replies = []
for c in convs:
    last = ts(c.get("lastMessageAt"))
    if not last or last < SINCE_DT:
        continue
    msgs = c.get("messages") or []
    if c.get("totalMessages") and len(msgs) < int(c["totalMessages"]):
        truncated.append({"id": c.get("id"), "have": len(msgs),
                          "total": c.get("totalMessages")})
    prof = c.get("correspondentProfile") or {}
    inbound = [m for m in msgs
               if str(m.get("sender", "")).upper() != "ME" and ts(m.get("createdAt"))
               and ts(m["createdAt"]) >= SINCE_DT]
    # a conversation whose LAST message is theirs is a reply even if the message list was trimmed
    if not inbound and str(c.get("lastMessageSender", "")).upper() != "ME":
        inbound = [{"createdAt": c.get("lastMessageAt"), "body": c.get("lastMessageText"),
                    "sender": c.get("lastMessageSender"), "__from_summary": True}]
    for m in inbound:
        replies.append({
            "conversation_id": c.get("id"),
            "name": " ".join(x for x in (prof.get("firstName"), prof.get("lastName")) if x),
            "linkedin_id": prof.get("linkedin_id"),
            "profile_url": prof.get("profileUrl"),
            "slug": slug(prof.get("profileUrl")),
            "headline": prof.get("headline"),
            "time": ts(m.get("createdAt")).isoformat(),
            "body": str(m.get("body") or "")[:300],
            "from_summary_only": m.get("__from_summary", False),
            "linkedin_account_id": c.get("linkedInAccountId"),
        })
replies.sort(key=lambda r: r["time"])
print(f"INBOUND replies in window (HeyReach truth): {len(replies)}")
if truncated:
    print(f"  NOTE: {len(truncated)} conversation(s) returned fewer messages than totalMessages; "
          f"inbound detection for those falls back to the conversation summary")

# --------------------------------------------------- 2. WF-1 executions over the same window
ex = n8n("/api/v1/executions", {"workflowId": WF1, "limit": 250})
execs = [e for e in (ex.get("data") or []) if ts(e.get("startedAt")) and ts(e["startedAt"]) >= SINCE_DT]
print(f"\nWF-1 executions in window: {len(execs)}")

details = []
for e in sorted(execs, key=lambda r: r["startedAt"]):
    det = n8n(f"/api/v1/executions/{e['id']}", {"includeData": "true"})
    rd = (((det.get("data") or {}).get("resultData") or {}).get("runData") or {})

    def g(nm, key):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"].get(key)
        except Exception:
            return None

    lead = g("Normalize", "lead") or {}
    posted = "M7 Alert" in rd or "M7 Slack Alert" in rd or any(
        n for n in rd if "slack" in n.lower() and "suppress" not in n.lower())
    details.append({
        "id": e["id"], "startedAt": e.get("startedAt"), "status": e.get("status"),
        "event": g("Normalize", "event"),
        "lead_name": lead.get("full_name"), "lead_slug": slug(lead.get("profile_url")),
        "linkedin_id": lead.get("id"),
        "should_alert": g("M7 Alert Gate", "__should_alert"),
        "alert_reason": g("M7 Alert Gate", "__alert_reason"),
        "alert_suppressed_node": "M7 Alert Suppressed" in rd,
        "slack_nodes": [n for n in rd if "slack" in n.lower() or n.startswith("M7 Alert")],
        "labels_changed": "M7 IF Labels Changed" in rd,
        "reply_activity": "M7 Reply Activity" in rd,
        "nodes": list(rd.keys()),
    })
    time.sleep(0.05)

by_slug = {}
for d in details:
    if d["lead_slug"]:
        by_slug.setdefault(d["lead_slug"], []).append(d)

# ------------------------------------------------------------------- 3. per-reply verdict
print("\n" + "=" * 108)
print("PER-REPLY AUDIT")
print("=" * 108)
rows = []
for r in replies:
    match = by_slug.get(r["slug"], [])
    reply_execs = [m for m in match if str(m.get("event") or "").find("reply") >= 0]
    use = reply_execs or match
    pdp = pd(f"/v1/persons/search?term={urllib.parse.quote(r['profile_url'] or r['name'])}"
             f"&fields=custom_fields&exact_match=false") if r["profile_url"] else {}
    items = ((pdp or {}).get("data") or {}).get("items") or []
    person_id = items[0]["item"]["id"] if items else None
    verdict = ("processed" if use else "NO WF-1 EXECUTION")
    alerted = None
    reason = None
    if use:
        alerted = any(m["should_alert"] is True for m in use)
        reason = "; ".join(sorted({str(m["alert_reason"]) for m in use}))
    rows.append({**r, "person_id": person_id, "execs": [m["id"] for m in use],
                 "verdict": verdict, "alerted": alerted, "alert_reason": reason,
                 "labels_changed": any(m["labels_changed"] for m in use) if use else False,
                 "reply_activity": any(m["reply_activity"] for m in use) if use else False})
    print(f"\n{r['time']}  {r['name']}  ({r['slug']})")
    print(f"   headline : {str(r['headline'])[:80]}")
    print(f"   message  : {r['body'][:140]!r}")
    print(f"   WF-1     : {verdict}  execs={[m['id'] for m in use]}")
    if use:
        print(f"   alert    : should_alert={alerted}  reason={reason}")
        print(f"   CRM      : labels_changed={rows[-1]['labels_changed']} "
              f"reply_activity={rows[-1]['reply_activity']}")
    print(f"   pipedrive: person {person_id}")

# ------------------------------------------------------------------------- 4. summary
print("\n" + "=" * 108)
print("SUMMARY")
print("=" * 108)
noexec = [r for r in rows if r["verdict"] != "processed"]
alerted = [r for r in rows if r["alerted"] is True]
suppressed = [r for r in rows if r["alerted"] is False]
print(f"  HeyReach inbound replies in window : {len(rows)}")
print(f"  processed by WF-1                  : {len(rows) - len(noexec)}")
print(f"  NO WF-1 execution                  : {len(noexec)}")
print(f"  alert FIRED (would post to Slack)  : {len(alerted)}")
print(f"  alert SUPPRESSED                   : {len(suppressed)}")
print(f"  suppression reasons                : "
      f"{dict(Counter(r['alert_reason'] for r in suppressed))}")
for r in noexec:
    print(f"    UNPROCESSED: {r['time']} {r['name']} ({r['slug']})")

print(f"\n  WF-1 execution events in window: "
      f"{dict(Counter(d['event'] for d in details))}")
print(f"  alert reasons across all executions: "
      f"{dict(Counter(d['alert_reason'] for d in details if d['alert_reason']))}")

with open(os.path.join(HERE, "wf1-release-evidence", "t1_weekend_reply_audit.json"), "w",
          encoding="utf-8") as f:
    json.dump({"window": {"since": SINCE, "now": NOW.isoformat()},
               "replies": rows, "wf1_executions": details,
               "truncated_conversations": truncated}, f, indent=2, ensure_ascii=False,
              default=str)
print("\nwrote wf1-release-evidence/t1_weekend_reply_audit.json")
