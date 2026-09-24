"""MELISA PACK item 3 — daily LinkedIn-channel reconciliation.

Turns the 3.7% arrival gap from an unknown into a watched number. A webhook that never arrives
leaves no execution to alert on, so this is the only way the LinkedIn channel can be monitored:
compare HeyReach's own truth against the CRM, every day, and emit one digest line.

Digest line:
  LinkedIn channel: 41 touches yesterday, 40 in CRM, gaps: 1 (Person-fbbb498b / Acme)

Read-only. Writes nothing to Pipedrive or HeyReach; the only side effect is the Slack digest line,
and even that is suppressed unless SLACK_WEBHOOK is set (so a cron dry-run is silent).

Persists a JSONL ledger, because execution retention is ~13h and a gap trend needs history that
outlives it - the same reason WF-2S keeps its own ledger.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "wf1-release-evidence", "linkedin_reconcile_ledger.jsonl")
HRK = os.environ["HEYREACH_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SLACK = os.environ.get("SLACK_WEBHOOK", "")
LOOKBACK_H = int(os.environ.get("LOOKBACK_HOURS", "24"))
UA = "Mozilla/5.0 janea-daily/1.0"
F_LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
F_MEMBER = "010fc51128116e8c73ae2b33fd52fd4537451f2b"
F_PUBLIC = "2339d1c7a7cda05651dff68ff82b2d56b20e241d"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
# pre-production test campaigns: an accepted gap by owner decision, never counted or backfilled
EXCLUDE_CAMPAIGNS = {510736, 510448, 506813, 505075}


def hr(path, body, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.heyreach.io/api/public" + path,
                                       data=json.dumps(body).encode(), method="POST",
                                       headers={"X-API-KEY": HRK, "Accept": "application/json",
                                                "Content-Type": "application/json",
                                                "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


def pd(path, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path,
                                       headers={"x-api-token": PDT, "User-Agent": UA})
            with urllib.request.urlopen(r, timeout=180) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(5 * (i + 1))
                continue
            return {"__err": e.code}
    return {}


def norm_li(u):
    if not u:
        return None
    s = str(u).strip().lower().split("?")[0].rstrip("/")
    m = re.search(r"/in/([^/]+)$", s)
    return m.group(1) if m else s


def main():
    now = datetime.now(timezone.utc)
    cut = now - timedelta(hours=LOOKBACK_H)
    cut_s = cut.strftime("%Y-%m-%dT%H:%M:%SZ")

    camps = [c for c in ((hr("/campaign/GetAll", {"offset": 0, "limit": 100}) or {}).get("items")
                         or []) if c["id"] not in EXCLUDE_CAMPAIGNS]
    touches = []
    for c in camps:
        off = 0
        while True:
            d = hr("/campaign/GetLeadsFromCampaign",
                   {"campaignId": c["id"], "offset": off, "limit": 100})
            its = (d or {}).get("items") or []
            for L in its:
                p = L.get("linkedInUserProfile") or {}
                conn = str(L.get("leadConnectionStatus") or "")
                msg = str(L.get("leadMessageStatus") or "")
                if not (conn in ("ConnectionSent", "ConnectionAccepted")
                        or msg in ("MessageSent", "MessageReply")):
                    continue
                # "yesterday's touches" = last action (or creation) inside the window
                when = str(L.get("lastActionTime") or L.get("creationTime") or "")
                if not when or when < cut_s:
                    continue
                touches.append({
                    "slug": norm_li(p.get("profileUrl")),
                    "member_key": str(p.get("linkedin_id") or "") or None,
                    "name": f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip(),
                    "company": p.get("companyName"), "campaign_id": c["id"],
                    "campaign": c["name"], "when": when,
                    "accepted": conn == "ConnectionAccepted",
                    "replied": msg == "MessageReply"})
            off += len(its)
            if len(its) < 100 or off >= int((d or {}).get("totalCount") or 0):
                break

    by_li, by_mem, by_pub, leads_by_person = {}, {}, {}, {}
    cursor = None
    while True:
        d = pd("/api/v2/persons?limit=500&sort_by=id&sort_direction=asc"
               + (f"&cursor={cursor}" if cursor else ""))
        if d.get("__err"):
            print(f"pipedrive persons failed: {d}", file=sys.stderr)
            return 2
        for p in d.get("data") or []:
            cf = p.get("custom_fields") or {}
            k = norm_li(cf.get(F_LI))
            if k:
                by_li.setdefault(k, p)
            if cf.get(F_MEMBER) not in (None, ""):
                by_mem.setdefault(str(cf[F_MEMBER]), p)
            if cf.get(F_PUBLIC) not in (None, ""):
                for part in str(cf[F_PUBLIC]).lower().split(","):
                    if part.strip():
                        by_pub.setdefault(part.strip(), p)
        cursor = (d.get("additional_data") or {}).get("next_cursor")
        if not cursor:
            break
    start = 0
    while True:
        d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
        b = d.get("data") or []
        for L in b:
            if L.get("person_id"):
                leads_by_person.setdefault(L["person_id"], []).append(L)
        more = ((d.get("additional_data") or {}).get("pagination") or {})
        start += len(b)
        if not b or not more.get("more_items_in_collection"):
            break

    gaps = []
    for t in touches:
        person = (by_li.get(t["slug"])
                  or (by_mem.get(t["member_key"]) if t["member_key"] else None)
                  or by_pub.get(t["slug"]))
        lead = None
        if person:
            cands = leads_by_person.get(person["id"], [])
            lead = next((L for L in cands
                         if str(L.get(F_LEADCAMP) or "") == t["campaign"]), None) \
                or next((L for L in cands
                         if str(L.get("title") or "").startswith(f"{t['campaign_id']} - ")), None)
        if not (person and lead):
            gaps.append({**t, "person_id": person["id"] if person else None,
                         "missing": "lead" if person else "person+lead"})

    n, g = len(touches), len(gaps)
    who = ", ".join(f"{x['name']} / {x.get('company') or '?'}" for x in gaps[:5])
    if g > 5:
        who += f", +{g - 5} more"
    line = (f"LinkedIn channel: {n} touches in the last {LOOKBACK_H}h, {n - g} in CRM, "
            f"gaps: {g}" + (f" ({who})" if g else ""))
    print(line)
    if g:
        print(f"  gap rate {100.0 * g / max(n, 1):.1f}%  "
              f"accepted among gaps: {sum(1 for x in gaps if x['accepted'])}, "
              f"replied: {sum(1 for x in gaps if x['replied'])}")

    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": LOOKBACK_H,
                            "touches": n, "in_crm": n - g, "gaps": g,
                            "gap_detail": gaps[:50]}, ensure_ascii=False) + "\n")
    print(f"appended to {LEDGER}")

    if SLACK:
        payload = {"text": ("⚠️ " if g else "✅ ") + line}
        req = urllib.request.Request(SLACK, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as x:
                print(f"slack -> {x.status}")
        except urllib.error.HTTPError as e:
            print(f"slack failed: {e.code}", file=sys.stderr)
    else:
        print("SLACK_WEBHOOK not set - digest line printed only (safe for a dry cron run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
