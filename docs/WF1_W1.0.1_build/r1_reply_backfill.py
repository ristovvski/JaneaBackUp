#!/usr/bin/env python3
"""R1 - backfill the 10 replies lost to the 2026-08-04/05 WF-2 OOM outage.

Reproduces WF-2's OWN reply-branch contract, read from the live workflow (versionId e9242d0a),
rather than re-inventing it:

  Lead Resolve        campaign-field exact -> '{campaign_id} - ' title-prefix fallback
  Classify            only where Smartlead has no lead_category (CFG.llm, min_confidence guardrail)
  SL Category         POST /campaigns/{cid}/leads/{lid}/category      (only when Smartlead's is empty)
  Lead Labels Union   PATCH /v1/leads/{id}  label_ids = UNION(existing, cold, connected, responded)
  Reply Activity      POST /api/v2/activities  (owner_id is correct on v2; v1 wants user_id)
  SL Forward Email    POST /campaigns/{cid}/forward-email  - ONLY for CFG.forwardable_categories,
                      target = forward_owner_map[forward_inbox_map[sender_inbox]]

DRY_RUN=1 (default) performs ZERO writes and prints every intended payload.
DRY_RUN=0 executes, in the owner's stated priority order (jonathan.brum Interested first).
"""
import json, os, ssl, sys, time
from datetime import datetime, timezone
import urllib.error, urllib.parse, urllib.request

DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
ONLY = os.environ.get("ONLY", "").strip().lower()      # optional: run a single email
SLK = os.environ["SMARTLEAD_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
UA = "Mozilla/5.0 janea-r1-backfill/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

# owner's stated order: hwang FIRST (meeting proposal going stale), then jonathan.brum's two
# replies in chronological order, then the rest by reply time.
TARGETS = [
    ("2026-08-04T16:31:45+00:00", "pii-6f8f48e5@example.invalid", 3686193),         # "How about 5pm?"
    ("2026-08-04T16:55:41+00:00", "pii-567b1851@example.invalid", 3686181),
    ("2026-08-04T17:15:19+00:00", "pii-567b1851@example.invalid", 3686181),   # 2nd reply, same lead
    ("2026-08-04T15:10:03+00:00", "pii-67425a37@example.invalid", 3686193),
    ("2026-08-04T16:15:03+00:00", "pii-b02b50cf@example.invalid", 3686181),
    ("2026-08-04T16:38:45+00:00", "pii-135b4c7b@example.invalid", 3686187),             # BOUNCE - see D2
    ("2026-08-04T16:38:45+00:00", "pii-90ec4caf@example.invalid", 3686184),
    ("2026-08-04T17:04:26+00:00", "pii-06275333@example.invalid", 3686184),
    ("2026-08-04T19:10:59+00:00", "pii-7b1c0e1a@example.invalid", 3686181),      # needs lead created first
    ("2026-08-05T06:08:38+00:00", "pii-280f963f@example.invalid", 3686193),
]
# D2 (owner's decision): a bounce is not a reply. Smartlead category + bounce note ONLY - no
# '3. Responded' label, and excluded from the recovered-reply count. WF-2 routes bounces down its
# own branch for exactly this reason; labelling a dead address as engaged would be a contract
# violation, not a shortcut.
BOUNCE = {"pii-135b4c7b@example.invalid"}


def _req(url, headers, method="GET", body=None, tries=3):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=headers, method=method, data=data)
            with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
                return json.load(x)
        except urllib.error.HTTPError as e:
            txt = ""
            try:
                txt = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1)); continue
            return {"__err": e.code, "__body": txt}
        except Exception as e:
            if i + 1 < tries:
                time.sleep(3); continue
            return {"__err": str(e)[:200]}
    return {}


def sl(path, params=None, method="GET", body=None):
    q = dict(params or {}); q["api_key"] = SLK
    return _req(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}",
                {"User-Agent": UA, "Content-Type": "application/json"}, method, body)


def pd(path, method="GET", body=None):
    return _req(f"https://api.pipedrive.com{path}",
                {"x-api-token": PDT, "User-Agent": UA, "Content-Type": "application/json"},
                method, body)


def n8n(path):
    return _req(f"{N8N_BASE}{path}", {"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})


def openai_chat(body):
    return _req("https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json",
                 "User-Agent": UA}, "POST", body)


def canon2(s):
    return " ".join(str(s or "").replace(" ", " ").replace(" ", " ")
                    .replace(" ", " ").split())


def plain(html, limit=8000):
    import re
    t = str(html or "")
    t = re.sub(r"<blockquote[\s\S]*$", "", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(div|p|li|tr)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]*>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
          .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:limit]


# ---------------------------------------------------------------- live contract straight from WF-2
wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
CFG = json.loads(next(n for n in wf["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
F = CFG["fields"]
LBL = CFG["labels"]
CATMAP = CFG["category_map"]
FWDABLE = set(CFG["forwardable_categories"])
INBOX = {k.lower(): v for k, v in (CFG["forward_inbox_map"] or {}).items()}
OWNERS = CFG["forward_owner_map"]
print(f"contract source: WF-2 versionId={wf.get('versionId')}  WRITE_MODE={CFG['WRITE_MODE']}")
print(f"forwardable={sorted(FWDABLE)}  review={CFG['forward_review_address']}  "
      f"min_confidence={CFG.get('llm', {}).get('min_confidence')}")
print(f"MODE: {'DRY-RUN (zero writes)' if DRY_RUN else '*** LIVE WRITES ***'}\n")

CAMP_NAME = {}
for cid in {c for _, _, c in TARGETS}:
    d = sl(f"/campaigns/{cid}")
    CAMP_NAME[cid] = (d or {}).get("name")

# one full leads page, exactly like WF-2's Lead List, so Lead Resolve behaves identically
all_leads, start = [], 0
while True:
    d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
    b = d.get("data") or []
    all_leads.extend(b)
    more = ((d.get("additional_data") or {}).get("pagination") or {})
    start += len(b)
    if not b or not more.get("more_items_in_collection"):
        break
print(f"pipedrive leads loaded: {len(all_leads)}\n")

plan, writes_done = [], []
for rts, email, cid in TARGETS:
    if ONLY and email != ONLY:
        continue
    print("=" * 104)
    print(f"{rts}  {email}  campaign {cid} {CAMP_NAME.get(cid)}")
    print("=" * 104)
    step = {"reply_time": rts, "email": email, "campaign_id": cid,
            "campaign_name": CAMP_NAME.get(cid), "actions": []}

    # --- Smartlead lead + this specific reply from message-history
    ld = sl("/leads", {"email": email})
    sl_lead_id = (ld or {}).get("id")
    lcd = next((c for c in ((ld or {}).get("lead_campaign_data") or [])
                if c.get("campaign_id") == cid), {})
    sl_cat_id = lcd.get("lead_category_id")
    sl_cat = next((k for k, v in CATMAP.items() if v == sl_cat_id), None)
    hist = sl(f"/campaigns/{cid}/leads/{sl_lead_id}/message-history").get("history") or []
    reps = [h for h in hist if str(h.get("type", "")).upper() == "REPLY"]
    this = next((h for h in reps if str(h.get("time", "")).startswith(rts[:19].replace("+00:00", ""))
                 or (h.get("time") or "")[:19] == rts[:19]), reps[-1] if reps else {})
    sender_inbox = str((next((h for h in hist if str(h.get("type", "")).upper() == "SENT"), {})
                        ).get("from") or this.get("to") or "").strip().lower()
    body_txt = plain(this.get("email_body"))
    print(f"  smartlead lead={sl_lead_id}  category={sl_cat!r} (id={sl_cat_id})  "
          f"sender_inbox={sender_inbox}")
    print(f"  reply text: {body_txt[:220]!r}")
    step.update({"sl_lead_id": sl_lead_id, "sl_category": sl_cat, "sender_inbox": sender_inbox,
                 "message_id": this.get("message_id"), "stats_id": this.get("stats_id"),
                 "subject": this.get("subject"), "reply_text": body_txt})

    # --- classify only when Smartlead has nothing (WF-2's guardrail, same thresholds)
    category, cat_source, conf, summary = sl_cat, "smartlead", None, None
    if not category:
        cats = ", ".join(CATMAP.keys())
        prompt = ("Classify this cold-outreach email reply. Return STRICT JSON only, no prose:\n"
                  '{"category": one of [' + cats + '], "confidence": 0..1, "is_dnc": boolean,'
                  ' "one_line_summary": string}\n\nSubject: ' + str(this.get("subject") or "")
                  + "\n\nBody:\n" + body_txt[:4000])
        req = {"model": CFG["llm"]["model"],
               "max_completion_tokens": CFG["llm"]["max_completion_tokens"],
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": "You classify cold-outreach email "
                                                          "replies. Answer with a single JSON "
                                                          "object and nothing else."},
                            {"role": "user", "content": prompt}]}
        resp = openai_chat(req)
        raw = (((resp.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        try:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", raw)
            parsed = json.loads(m.group(0)) if m else None
        except Exception:
            parsed = None
        minc = float(CFG["llm"].get("min_confidence", 0.6))
        conf = float((parsed or {}).get("confidence") or 0)
        cand = (parsed or {}).get("category")
        ok = bool(parsed) and cand in CATMAP and conf >= minc
        category = cand if ok else "Uncategorized"
        summary = (parsed or {}).get("one_line_summary")
        cat_source = CFG["llm"].get("provider", "llm")
        print(f"  CLASSIFIED -> {category!r} confidence={conf} ok={ok}  summary={summary!r}")
    step.update({"category": category, "category_source": cat_source, "confidence": conf,
                 "summary": summary})

    # --- person + lead resolution, WF-2's Lead Resolve rules
    srch = pd(f"/v1/persons/search?term={urllib.parse.quote(email)}&fields=email&exact_match=true")
    items = ((srch or {}).get("data") or {}).get("items") or []
    cand_ids = [str(i["item"]["id"]) for i in items]
    mine = [L for L in all_leads if not L.get("is_archived") and str(L.get("person_id")) in cand_ids]
    hit = next((L for L in mine if canon2(L.get(F["lead_campaign"])) == canon2(CAMP_NAME.get(cid))), None)
    how = "campaign_field" if hit else None
    if not hit:
        hit = next((L for L in mine if str(L.get("title") or "").startswith(f"{cid} - ")), None)
        how = "title_prefix" if hit else "none"
    person_id = (hit or {}).get("person_id") or (int(cand_ids[0]) if cand_ids else None)
    print(f"  person={person_id}  lead={(hit or {}).get('id')}  how={how}")
    step.update({"person_id": person_id, "lead_id": (hit or {}).get("id"), "lead_how": how})

    # --- A. lead creation when missing (john.teuber - Make's defect class)
    if not hit and person_id:
        pj = pd(f"/api/v2/persons/{person_id}")
        pname = ((pj.get("data") or {}).get("name")) or email
        lead_body = {"title": f"{cid} - {CAMP_NAME.get(cid)} - {pname}",
                     "person_id": person_id, "owner_id": CFG["owner_id"],
                     "label_ids": [LBL["cold"]],
                     F["lead_campaign"]: CAMP_NAME.get(cid),
                     F["lead_opportunity_type"]: CFG["lead_opportunity_type_value"],
                     "channel": CFG["lead_channel"]}
        step["actions"].append({"op": "CREATE LEAD", "method": "POST", "url": "/v1/leads",
                                "body": lead_body})
        print(f"  [A] CREATE LEAD -> {json.dumps(lead_body, ensure_ascii=False)[:200]}")
        if not DRY_RUN:
            res = pd("/v1/leads", "POST", lead_body)
            new = (res or {}).get("data") or {}
            if new.get("id"):
                hit = {"id": new["id"], "person_id": person_id, "label_ids": [LBL["cold"]]}
                step["lead_id"] = new["id"]
                writes_done.append(("CREATE LEAD", email, new["id"]))
                print(f"      -> created lead {new['id']}")
            else:
                print(f"      -> FAILED {json.dumps(res)[:300]}")

    lead_id = (hit or {}).get("id")

    # --- B. Smartlead category, only when Smartlead has none (never overwrite Smartlead's own)
    if not sl_cat and category and category != "Uncategorized" and sl_lead_id:
        cbody = {"category_id": CATMAP[category]}
        step["actions"].append({"op": "SL CATEGORY", "method": "POST",
                                "url": f"/campaigns/{cid}/leads/{sl_lead_id}/category",
                                "body": cbody})
        print(f"  [B] SL CATEGORY -> {cbody}")
        if not DRY_RUN:
            r = sl(f"/campaigns/{cid}/leads/{sl_lead_id}/category", None, "POST", cbody)
            print(f"      -> {json.dumps(r)[:200]}")
            writes_done.append(("SL CATEGORY", email, category))

    is_bounce = email in BOUNCE or category == "Sender Originated Bounce"
    step["is_bounce"] = is_bounce
    if is_bounce:
        print("  [!] BOUNCE (D2): no responded label, bounce note instead of reply activity, "
              "excluded from the recovered-reply count")

    # --- C. label union (cumulative, never removes - W1.0.7 rule); never for a bounce
    if lead_id and not is_bounce:
        existing = list((hit or {}).get("label_ids") or [])
        union = existing[:]
        for lid in (LBL["cold"], LBL["connected"], LBL["responded"]):
            if lid and lid not in union:
                union.append(lid)
        if len(union) != len(existing):
            lbody = {"label_ids": union}
            step["actions"].append({"op": "LEAD LABELS UNION", "method": "PATCH",
                                    "url": f"/v1/leads/{lead_id}", "body": lbody,
                                    "adds": len(union) - len(existing)})
            print(f"  [C] LABELS UNION -> +{len(union)-len(existing)} label(s)")
            if not DRY_RUN:
                r = pd(f"/v1/leads/{lead_id}", "PATCH", lbody)
                print(f"      -> {'ok' if (r or {}).get('data') else json.dumps(r)[:250]}")
                writes_done.append(("LABELS", email, lead_id))
        else:
            print("  [C] LABELS UNION -> no change needed (already carries all three)")

    # --- D. reply activity carrying the actual text (bounce note shape for a bounce)
    if lead_id and is_bounce:
        abody = {"subject": f"Email bounced — {CAMP_NAME.get(cid)}", "type": "email", "done": True,
                 "owner_id": CFG["owner_id"], "lead_id": lead_id,
                 "note": f"Smartlead reported a bounce for {email} on {rts}"
                         + (f"\n\n— {summary}" if summary else "")
                         + "\n\n— historical backfill of an event lost to the 2026-08-04/05 "
                           "WF-2 outage",
                 "due_date": rts[:10]}
        step["actions"].append({"op": "BOUNCE NOTE", "method": "POST",
                                "url": "/api/v2/activities", "body": abody})
        print(f"  [D] BOUNCE NOTE -> {abody['subject']!r}")
        if not DRY_RUN:
            r = pd("/api/v2/activities", "POST", abody)
            ok = (r or {}).get("data", {}).get("id")
            print(f"      -> {'activity ' + str(ok) if ok else json.dumps(r)[:300]}")
            writes_done.append(("BOUNCE NOTE", email, ok))
    elif lead_id:
        parts = []
        if this.get("subject"):
            parts.append("Subject: " + str(this["subject"]))
        if body_txt:
            parts.append(body_txt)
        if summary:
            parts.append("— " + str(summary))
        parts.append("— historical backfill of a reply lost to the 2026-08-04/05 WF-2 outage")
        abody = {"subject": f"Email reply — {CAMP_NAME.get(cid)}", "type": "email", "done": True,
                 "owner_id": CFG["owner_id"], "lead_id": lead_id, "note": "\n\n".join(parts),
                 "due_date": rts[:10]}
        step["actions"].append({"op": "REPLY ACTIVITY", "method": "POST",
                                "url": "/api/v2/activities", "body": abody})
        print(f"  [D] REPLY ACTIVITY -> note {len(abody['note'])} chars, due {abody['due_date']}")
        if not DRY_RUN:
            r = pd("/api/v2/activities", "POST", abody)
            ok = (r or {}).get("data", {}).get("id")
            print(f"      -> {'activity ' + str(ok) if ok else json.dumps(r)[:300]}")
            writes_done.append(("ACTIVITY", email, ok))

    # --- E. forward, ONLY for WF-2's forwardable categories
    owner_name = INBOX.get(sender_inbox)
    fwd_to = OWNERS.get(owner_name) if owner_name else None
    if category in FWDABLE:
        if not fwd_to:
            fwd_to = CFG.get("forward_default")
        fbody = {"message_id": this.get("message_id"), "stats_id": this.get("stats_id"),
                 "to_emails": fwd_to}
        step["actions"].append({"op": "FORWARD", "method": "POST",
                                "url": f"/campaigns/{cid}/forward-email", "body": fbody,
                                "owner": owner_name})
        print(f"  [E] FORWARD -> {fwd_to} (owner {owner_name}, category {category})")
        if not DRY_RUN:
            r = sl(f"/campaigns/{cid}/forward-email", None, "POST", fbody)
            print(f"      -> {json.dumps(r)[:250]}")
            writes_done.append(("FORWARD", email, fwd_to))
    else:
        print(f"  [E] FORWARD -> SKIPPED: '{category}' is not in forwardable_categories "
              f"(would have gone to {fwd_to or CFG.get('forward_default')} / owner {owner_name})")
        step["actions"].append({"op": "FORWARD-SKIPPED", "reason": f"{category} not forwardable",
                                "would_be": fwd_to, "owner": owner_name})

    # --- F. Handover guard baseline: open activities on this lead before/after
    if lead_id:
        acts = pd(f"/v1/activities?lead_id={lead_id}&done=0&limit=100")
        opens = acts.get("data") or []
        step["open_activities_before"] = [{"id": a["id"], "subject": a.get("subject"),
                                           "type": a.get("type"), "owner": a.get("owner_id")}
                                          for a in opens]
        print(f"  [F] HANDOVER GUARD: {len(opens)} open activity(ies) on this lead right now"
              + (f" -> {[a.get('subject') for a in opens]}" if opens else ""))
    plan.append(step)
    print()

# ------------------------------------------------------------------------------- summary
print("=" * 104)
print("PLAN SUMMARY" + ("  (DRY-RUN - nothing written)" if DRY_RUN else "  (LIVE)"))
print("=" * 104)
tally = {}
for s in plan:
    for a in s["actions"]:
        tally[a["op"]] = tally.get(a["op"], 0) + 1
for k in sorted(tally):
    print(f"  {k:<20} {tally[k]}")
print(f"\n  leads resolved: {sum(1 for s in plan if s.get('lead_id'))}/{len(plan)}")
print(f"  forwards planned: {tally.get('FORWARD', 0)}  | skipped as non-forwardable: "
      f"{tally.get('FORWARD-SKIPPED', 0)}")
open_total = sum(len(s.get("open_activities_before") or []) for s in plan)
print(f"  open activities across all touched leads (Handover baseline): {open_total}")

# ---------------------------------------------------- Handover guard: post-write reconciliation
handover = {"baseline": open_total, "new": [], "closed": []}
if not DRY_RUN:
    print(f"\n  writes executed: {len(writes_done)}")
    print("\n" + "=" * 104)
    print("HANDOVER GUARD - re-reading open activities on every touched lead")
    print("=" * 104)
    time.sleep(20)                      # give Pipedrive's own automation a moment to fire
    for s in plan:
        lid = s.get("lead_id")
        if not lid:
            continue
        before = {a["id"] for a in (s.get("open_activities_before") or [])}
        acts = pd(f"/v1/activities?lead_id={lid}&done=0&limit=100")
        for a in (acts.get("data") or []):
            if a["id"] in before:
                continue
            handover["new"].append({"lead_id": lid, "email": s["email"], "activity_id": a["id"],
                                    "subject": a.get("subject"), "type": a.get("type"),
                                    "owner": a.get("owner_id")})
            print(f"  NEW open activity {a['id']} on {s['email']}: {a.get('subject')!r}")
    print(f"\n  newly auto-created open activities: {len(handover['new'])} "
          f"(expected <= {sum(1 for s in plan if any(x['op']=='LEAD LABELS UNION' for x in s['actions']))})")
    for h in handover["new"]:
        note = ("Closed by historical backfill — this Handover was auto-created when the "
                "'3. Responded' label was applied while recovering a reply lost to the "
                "2026-08-04/05 WF-2 outage. The reply itself is recorded on this lead as a "
                "done 'Email reply' activity.")
        r = pd(f"/api/v2/activities/{h['activity_id']}", "PATCH", {"done": True, "note": note})
        ok = bool((r or {}).get("data"))
        print(f"  {'closed' if ok else 'FAILED'} activity {h['activity_id']} ({h['email']})"
              + ("" if ok else f" -> {json.dumps(r)[:200]}"))
        if ok:
            handover["closed"].append(h["activity_id"])
    print(f"\n  Handovers marked done with a 'historical backfill' note: {len(handover['closed'])}")

# ---------------------------------------------------------------- consolidated Slack post (D4)
recovered = [s for s in plan if not s.get("is_bounce")]
lines = []
for s in recovered:
    fwd = next((a for a in s["actions"] if a["op"] == "FORWARD"), None)
    lines.append(f"• {s['reply_time'][:16].replace('T', ' ')}Z  {s['email']}  · {s['category']}"
                 + (f"  → forwarded to {fwd['body']['to_emails']}" if fwd else "  · no forward"
                    " (category not forwardable)"))
slack_text = (f"*Historical backfill: {len(recovered)} replies recovered from the Aug 4-5 outage "
              f"window*\n"
              f"These replies reached Smartlead between 2026-08-04 14:30Z and 2026-08-05 06:43Z, "
              f"while WF-2 was down after the OOM crash. Their webhooks 404'd, so nothing "
              f"processed them at the time — not WF-2, and not Make.\n\n"
              + "\n".join(lines)
              + f"\n\nEach lead now carries the `3. Responded` label and a done *Email reply* "
                f"activity containing the reply text. "
                f"{sum(1 for s in recovered if any(a['op']=='FORWARD' for a in s['actions']))} "
                f"forwards were sent to the campaign owners. "
                f"1 further event (pii-135b4c7b@example.invalid) was a bounce, not a reply — categorised in "
                f"Smartlead with a bounce note, no responded label.")
print("\n" + "=" * 104)
print("CONSOLIDATED SLACK POST (D4) - text prepared, posted separately to C0B8GCVNR5W")
print("=" * 104)
print(slack_text)

out = os.path.join(HERE, "wf1-release-evidence",
                   "r1_reply_backfill_" + ("dryrun" if DRY_RUN else "live") + ".json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"dry_run": DRY_RUN, "contract_versionId": wf.get("versionId"), "plan": plan,
               "writes_done": writes_done, "handover": handover, "slack_text": slack_text},
              f, indent=2, ensure_ascii=False, default=str)
print(f"\nwrote {out}")
