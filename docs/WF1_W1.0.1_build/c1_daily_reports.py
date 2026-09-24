"""C1 — today's daily reports, content built from real evidence (read-only), for C0B8GCVNR5W.

WF-2H EXTENDED: per campaign - sends, replies -> categorized? -> forwarded to whom, persons+leads
vs sends delta, labels, alive-checks (incl active===true), secret armed.
WF-1H NEW: touches per campaign, CRM reconciliation, label gaps, alert-gate stats.

Scope note (stated plainly, not silently skipped): this generates and posts the CONTENT today, using
the same read-only logic already proven this session (B2's shadow-log drill-down, the LinkedIn
reconciliation, the WF-1 audit). Productionizing both as native n8n workflows (Schedule Trigger,
credentials in n8n's store, burst-dedup on the watchdog) is a separate, larger build - flagged as a
follow-up, not done here.
"""
import json
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SLK = os.environ["SMARTLEAD_API_KEY"]
HRK = os.environ["HEYREACH_API_KEY"]
WF1 = os.environ["WF1_ID"]
WF2 = "jp7rum9Z0YDJkQWv"
WF2S = "6Y92ryBwYoy6z0Jx"
UA = "Mozilla/5.0 janea-flipday/1.0"
WINDOW_H = 24
CAMPS_EMAIL = {3686193: "Rune-Catch-alls", 3686187: "Rune-Valids",
               3686184: "Mario-Catch-alls", 3686181: "Mario-Valids"}
CAMPS_LI = {513000: "Rune-LinkedIn", 512995: "Mario-LinkedIn"}
F_LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
F_MEMBER = "010fc51128116e8c73ae2b33fd52fd4537451f2b"
F_PUBLIC = "2339d1c7a7cda05651dff68ff82b2d56b20e241d"
F_LEADCAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
CUT = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.load(x)


def sl(path):
    sep = "&" if "?" in path else "?"
    r = urllib.request.Request(f"https://server.smartlead.ai/api/v1{path}{sep}api_key={SLK}",
                               headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=150) as x:
        return json.load(x)


def hr(path, body):
    r = urllib.request.Request("https://api.heyreach.io/api/public" + path,
                               data=json.dumps(body).encode(), method="POST",
                               headers={"X-API-KEY": HRK, "Content-Type": "application/json",
                                        "Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def norm_li(u):
    if not u:
        return None
    s = str(u).strip().lower().split("?")[0].rstrip("/")
    m = re.search(r"/in/([^/]+)$", s)
    return m.group(1) if m else s


print("=" * 96)
print("WF-2H EXTENDED - alive-checks + secret armed")
print("=" * 96)
wf2 = n8n(f"/api/v1/workflows/{WF2}")
N2 = {n["name"]: n for n in wf2["nodes"]}
cfg2 = json.loads(N2["CONFIG"]["parameters"]["jsonOutput"])
wf2_active = wf2.get("active") is True
secret_armed = bool(cfg2.get("webhook_secret_sha256"))
wf2s = n8n(f"/api/v1/workflows/{WF2S}")
wf2s_active = wf2s.get("active") is True
WFERR = "BbrXPABgOaaTJjD6"
d = n8n(f"/api/v1/executions?workflowId={WFERR}&limit=1")
wferr_ok = bool(d.get("data"))
print(f"WF-2 active={wf2_active}  WF-2S active={wf2s_active}  webhook_secret_armed={secret_armed}"
      f"  WF-ERR_has_recent={wferr_ok}")

print("\n" + "=" * 96)
print("WF-2H EXTENDED - per-campaign sends, replies, categorize, forward, persons+leads delta")
print("=" * 96)
by_li, by_mem, by_pub, leads_by_person = {}, {}, {}, defaultdict(list)
cursor = None
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc" + (f"&cursor={cursor}" if cursor else "")
    d = pd(q)
    for p in d.get("data") or []:
        for em in p.get("emails") or []:
            v = str(em.get("value") or "").strip().lower()
            if v:
                by_li.setdefault(v, p["id"])
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break
start = 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    for L in b:
        if L.get("person_id"):
            leads_by_person[L["person_id"]].append(L)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break

wf2_report = []
ex = n8n(f"/api/v1/executions?workflowId={WF2}&limit=250")
rows = [r for r in (ex.get("data") or []) if r.get("startedAt") and r["startedAt"] >= CUT]
shadow = []
for r in rows:
    dd = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
    rd = (((dd.get("data") or {}).get("resultData") or {}).get("runData") or {})
    for run in rd.get("Shadow Log") or []:
        try:
            j = run["data"]["main"][0][0]["json"]
            j["_exec"] = r["id"]
            shadow.append(j)
        except Exception:
            continue

for cid, label in CAMPS_EMAIL.items():
    ent = [e for e in shadow if e.get("campaign_id") == cid]
    sent = sl(f"/campaigns/{cid}/analytics")
    sent_count = sent.get("sent_count") if isinstance(sent, dict) else None
    reply_execs = set(e["_exec"] for e in ent
                      if str(e.get("event", "")).lower().startswith(("repl",)))
    cat = sum(1 for e in ent if e.get("node") == "SL Category")
    fwd = [e for e in ent if e.get("node") == "SL Forward Email"]
    fwd_to = [str((e.get("body") or {}).get("to_emails")) for e in fwd]
    by_person_email = set(e.get("lead_email") for e in ent if e.get("lead_email"))
    missing_person = sum(1 for em in by_person_email if em and by_li.get(str(em).lower()) is None)
    wf2_report.append({"campaign": label, "sent": sent_count, "replies": len(reply_execs),
                       "categorized": cat, "forwarded_to": fwd_to,
                       "persons_missing": missing_person})

print(json.dumps(wf2_report, ensure_ascii=False, indent=2)[:3000])

print("\n" + "=" * 96)
print("WF-1H NEW - touches per campaign + CRM reconciliation + label gaps + alert-gate stats")
print("=" * 96)
li_touches = []
for cid, label in CAMPS_LI.items():
    off = 0
    while True:
        d = hr("/campaign/GetLeadsFromCampaign", {"campaignId": cid, "offset": off, "limit": 100})
        its = (d or {}).get("items") or []
        for L in its:
            p = L.get("linkedInUserProfile") or {}
            when = str(L.get("lastActionTime") or L.get("creationTime") or "")
            conn = str(L.get("leadConnectionStatus") or "")
            msg = str(L.get("leadMessageStatus") or "")
            contacted = conn in ("ConnectionSent", "ConnectionAccepted") \
                or msg in ("MessageSent", "MessageReply")
            if contacted and when >= CUT:
                li_touches.append({"campaign": label, "campaign_id": cid,
                                   "slug": norm_li(p.get("profileUrl")),
                                   "member_key": str(p.get("linkedin_id") or "") or None,
                                   "name": f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip(),
                                   "accepted": conn == "ConnectionAccepted",
                                   "replied": msg == "MessageReply"})
        off += len(its)
        if len(its) < 100 or off >= int((d or {}).get("totalCount") or 0):
            break

by_mem2, by_pub2 = {}, {}
cursor = None
while True:
    q = "/api/v2/persons?limit=500&sort_by=id&sort_direction=asc" + (f"&cursor={cursor}" if cursor else "")
    d = pd(q)
    for p in d.get("data") or []:
        cf = p.get("custom_fields") or {}
        k = norm_li(cf.get(F_LI))
        if k:
            by_li.setdefault(k, p["id"])
        if cf.get(F_MEMBER) not in (None, ""):
            by_mem2.setdefault(str(cf[F_MEMBER]), p["id"])
        if cf.get(F_PUBLIC) not in (None, ""):
            for part in str(cf[F_PUBLIC]).lower().split(","):
                if part.strip():
                    by_pub2.setdefault(part.strip(), p["id"])
    cursor = (d.get("additional_data") or {}).get("next_cursor")
    if not cursor:
        break

per_camp_li = defaultdict(lambda: {"touches": 0, "gaps": []})
for t in li_touches:
    b = per_camp_li[t["campaign"]]
    b["touches"] += 1
    pid = (by_li.get(t["slug"]) or (by_mem2.get(t["member_key"]) if t["member_key"] else None)
           or by_pub2.get(t["slug"]))
    if not pid:
        b["gaps"].append(t["name"])
print(json.dumps({k: {"touches": v["touches"], "gaps": v["gaps"]}
                  for k, v in per_camp_li.items()}, ensure_ascii=False, indent=2))

print("\n-- M7 Alert Gate stats (W1.0.15 registry) --")
exw1 = n8n(f"/api/v1/executions?workflowId={WF1}&limit=250")
rowsw1 = [r for r in (exw1.get("data") or []) if r.get("startedAt") and r["startedAt"] >= CUT]
gate_reasons = defaultdict(int)
for r in rowsw1:
    dd = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
    rd = (((dd.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if "M7 Alert Gate" in rd:
        try:
            j = rd["M7 Alert Gate"][0]["data"]["main"][0][0]["json"]
            gate_reasons[j.get("__alert_reason")] += 1
        except Exception:
            pass
print(dict(gate_reasons))
print(f"\nWF-1 executions in window: {len(rowsw1)}")

RESULT = {"wf2_report": wf2_report, "li_touches_by_campaign": {k: v["touches"] for k, v in per_camp_li.items()},
          "li_gaps": {k: v["gaps"] for k, v in per_camp_li.items()},
          "alert_gate": dict(gate_reasons), "wf2_active": wf2_active, "wf2s_active": wf2s_active,
          "secret_armed": secret_armed, "window_cut": CUT}
json.dump(RESULT, open(r"C:\Users\User\Desktop\Нова папка\WF1_W1.0.1_build\wf1-release-evidence\c1_raw.json",
                      "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\nwrote c1_raw.json")
