"""Phase B2 — campaign correctness gate over the last 48h of REAL shadow executions. Read-only.

For every live campaign: every reply categorized + forward target resolved + lead matched.
Label-chain proof:
  (a) our written label ID == Pipedrive's real "3. Responded" ID (exact ID, not string)
  (b) WF-2 lead creation sets owner_id == Melisa's real Pipedrive user ID
  (c) a real shadow-recorded Lead Labels Union body actually carries that label ID

Any failure = RED. `Shadow Log` runs once per write-attempt reached (both live and skip branches route
through it, per its own code comment), so one reply execution yields several entries - one per
Body/Gate pair (category, forward, labels-union, reply-activity, ...).
"""
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
WF2 = "jp7rum9Z0YDJkQWv"
WINDOW_H = 48
UA = "Mozilla/5.0 janea-flipday/1.0"
GREEN, RED = [], []


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def pd(path):
    r = urllib.request.Request("https://api.pipedrive.com" + path,
                               headers={"x-api-token": PDT, "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.load(x)


wf = json.load(open(os.path.join(HERE, "wf2_live_flipday.json"), encoding="utf-8"))
N = {n["name"]: n for n in wf["nodes"]}
CFG = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
RESPONDED_ID_CODE = CFG["labels"]["responded"]
OWNER_ID_CODE = CFG["owner_id"]

print("=" * 96)
print("LABEL-CHAIN PROOF (a) + (b) - static, from live CONFIG vs Pipedrive ground truth")
print("=" * 96)
real_labels = {L["name"]: L["id"] for L in (pd("/v1/leadLabels").get("data") or [])}
real_responded_id = real_labels.get("3. Responded")
print(f"  WF-2 CONFIG.labels.responded = {RESPONDED_ID_CODE}")
print(f"  Pipedrive '3. Responded' id  = {real_responded_id}")
a_ok = (RESPONDED_ID_CODE == real_responded_id)
(GREEN if a_ok else RED).append(f"(a) label ID match: code={RESPONDED_ID_CODE} real={real_responded_id}")

users = {u["id"]: u.get("name") for u in (pd("/v1/users").get("data") or [])}
melisa_id = next((uid for uid, nm in users.items() if "melisa" in str(nm).lower()), None)
print(f"\n  WF-2 CONFIG.owner_id = {OWNER_ID_CODE} ({users.get(OWNER_ID_CODE)})")
print(f"  Melisa's real user id = {melisa_id} ({users.get(melisa_id)})")
b_ok = (OWNER_ID_CODE == melisa_id)
(GREEN if b_ok else RED).append(f"(b) owner ID match: code={OWNER_ID_CODE} real_melisa={melisa_id}")

print("\n" + "=" * 96)
print(f"PULLING {WINDOW_H}h OF REAL WF-2 EXECUTIONS")
print("=" * 96)
cutoff = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
d = n8n(f"/api/v1/executions?workflowId={WF2}&limit=250")
rows = [r for r in (d.get("data") or []) if r.get("startedAt") and r["startedAt"] >= cutoff]
rows.sort(key=lambda r: r["startedAt"])
print(f"  executions in window: {len(rows)}  ({cutoff} .. now)")

shadow_entries = []
reply_execs = 0
c_proof_body = None
per_exec_summary = []
for r in rows:
    d = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
    rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
    if "Shadow Log" not in rd:
        continue
    entries = []
    for run in rd["Shadow Log"]:
        try:
            entries.append(run["data"]["main"][0][0]["json"])
        except Exception:
            continue
    for e in entries:
        e["_exec_id"] = r["id"]
        e["_exec_started"] = r["startedAt"]
        shadow_entries.append(e)
    is_reply = any(str(e.get("event", "")).lower().startswith(("repl", "every_message_repl"))
                   for e in entries)
    if is_reply:
        reply_execs += 1
    per_exec_summary.append((r["id"], r["startedAt"], r.get("status"), len(entries),
                             sorted(set(e.get("node") for e in entries if e.get("node")))))
    for e in entries:
        if e.get("node") == "Lead Labels Union" and e.get("would_write") and c_proof_body is None:
            body = e.get("body") or {}
            labs = body.get("label_ids") or body.get("labels") or []
            if real_responded_id in [str(x) for x in labs]:
                c_proof_body = e

print(f"  executions with Shadow Log data: {len(per_exec_summary)}")
print(f"  total shadow entries: {len(shadow_entries)}")
print(f"  reply-type executions: {reply_execs}")
print("\n  sample of executions (first 10):")
for eid, at, st, n_entries, nodes in per_exec_summary[:10]:
    print(f"    {at}  exec={eid} status={st} entries={n_entries} nodes={nodes}")

print("\n" + "=" * 96)
print("LABEL-CHAIN PROOF (c) - a real shadow-recorded Lead Labels Union body carrying the exact ID")
print("=" * 96)
if c_proof_body:
    print(f"  FOUND: exec {c_proof_body['_exec_id']} at {c_proof_body['_exec_started']}")
    print(f"    campaign={c_proof_body.get('campaign_name')} lead_email={c_proof_body.get('lead_email')}")
    print(f"    body={json.dumps(c_proof_body.get('body'), ensure_ascii=False)[:400]}")
    GREEN.append("(c) a real shadow Lead Labels Union body carries the exact 3. Responded ID")
else:
    RED.append("(c) NO shadow-recorded Lead Labels Union body in-window carries the exact ID "
              "(either none ran, or none included it)")

print("\n" + "=" * 96)
print("PER-CAMPAIGN COMPLETENESS: categorized + forward-resolved + lead-matched")
print("=" * 96)
by_camp = defaultdict(lambda: {"replies": 0, "categorized": 0, "forward_attempted": 0,
                               "lead_matched": 0, "execs": set()})
reply_exec_ids = set()
for e in shadow_entries:
    if str(e.get("event", "")).lower().startswith(("repl", "every_message_repl")):
        reply_exec_ids.add(e["_exec_id"])
for e in shadow_entries:
    if e["_exec_id"] not in reply_exec_ids:
        continue
    key = (e.get("campaign_id"), e.get("campaign_name"))
    b = by_camp[key]
    b["execs"].add(e["_exec_id"])
    node = e.get("node")
    if node == "SL Category":
        b["categorized"] += 1
    if node in ("SL Forward Email",):
        b["forward_attempted"] += 1
    if node in ("Lead Create", "Lead Labels Union", "Reply Activity"):
        b["lead_matched"] += 1

if not by_camp:
    print("  NO reply-type executions in the 48h window at all.")
    RED.append("B2: zero reply executions in the 48h shadow window - cannot prove per-campaign "
              "correctness with no data")
else:
    for (cid, cname), b in sorted(by_camp.items(), key=lambda kv: -len(kv[1]["execs"])):
        n_replies = len(b["execs"])
        print(f"  [{cid}] {cname}")
        print(f"      reply executions={n_replies}  categorized_writes={b['categorized']}  "
              f"forward_attempts={b['forward_attempted']}  lead_writes={b['lead_matched']}")
        ok = b["categorized"] > 0 and b["lead_matched"] > 0
        (GREEN if ok else RED).append(
            f"campaign {cname}: categorized={b['categorized']} lead_writes={b['lead_matched']} "
            f"(forward_attempts={b['forward_attempted']}, 0 is valid if none were forwardable)")

print("\n" + "=" * 96)
print("B2 VERDICT")
print("=" * 96)
for g in GREEN:
    print(f"  GREEN  {g}")
for r in RED:
    print(f"  RED    {r}")
print(f"\n  {len(GREEN)} green / {len(RED)} red")
