#!/usr/bin/env python3
"""#28 — outbound activity backfill, EMAIL side. Campaign-scoped. Dry-run by default.

One activity per SENT, so Melisa can see Mario's outbound messages on the lead card.

IDEMPOTENCY — canonical key is `O|SL|<message_id>`. NOT stats_id: Smartlead reuses stats_id across
follow-up sends in the same thread (the message_id gains a `-slt<N>-` infix, stats_id does not), so
stats_id collided on 9 sends in 3686181 alone and `email_seq_number` was identical across every
collision. Where message_id itself repeats (3686184, one lead returned twice by the feed) the rows
are byte-identical duplicates, so collapsing them is correct — which a time-based key would not do.

Existing-activity check is by key, recorded in the note footer, so a re-run cannot double-write and
neither can the live path once it ships.

ROUTING follows the deal guard from this morning: an existing lead wins; if the person has no lead
but an OPEN DEAL, the activity goes on the DEAL; if neither, the send is reported as unroutable
rather than inventing a lead (that is exactly what created Andrea's duplicate).
"""
import argparse, html, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from collections import defaultdict

from deal_guard import activity_target, DealGuardBlocked

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
OWNER = 16340280

ap = argparse.ArgumentParser()
ap.add_argument("--campaign", type=int, default=3686181)
ap.add_argument("--live", action="store_true")
ap.add_argument("--limit-leads", type=int, default=0)
a = ap.parse_args()


def pd(p, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + p, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        return {"__err": f"HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}"}
    except Exception as e:
        return {"__err": str(e)[:140]}


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:140]}


def strip_html(s):
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", str(s or ""))
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


camp = sl(f"/campaigns/{a.campaign}")
cname = str((camp or {}).get("name") or a.campaign)
print(f"campaign {a.campaign}: {cname!r}")

# ---- pull every SENT, paging to exhaustion (a capped read would under-report silently)
sends = defaultdict(list)
offset, pages = 0, 0
while pages < 60:
    r = sl(f"/campaigns/{a.campaign}/leads-statistics", limit=100, offset=offset)
    rows = (r or {}).get("data") or []
    if not rows:
        break
    for row in rows:
        to = str(row.get("to") or "").strip().lower()
        if not to:
            continue
        for h in (row.get("history") or []):
            if str(h.get("type") or "").upper() != "SENT":
                continue
            sends[to].append({"stats_id": h.get("stats_id"),
                              "message_id": h.get("message_id"), "time": h.get("time"),
                              "subject": h.get("subject"), "seq": h.get("email_seq_number"),
                              "body": strip_html(h.get("email_body")),
                              "from": row.get("from")})
    if not r.get("hasMore"):
        break
    offset += 100
    pages += 1
tot = sum(len(v) for v in sends.values())
print(f"leads with sends: {len(sends)}   SENT events: {tot}   (pages walked {pages + 1})")
missing_id = sum(1 for v in sends.values() for s in v if not s["stats_id"])
print(f"  SENT entries lacking stats_id (would be unkeyable): {missing_id}")

if a.limit_leads:
    sends = dict(list(sends.items())[:a.limit_leads])

# ---- resolve each lead to its activity home
plan, unroutable, already = [], [], 0
for i, (email, evs) in enumerate(sends.items(), 1):
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(email)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    if not items:
        unroutable.append({"email": email, "why": "no person", "sends": len(evs)})
        continue
    pid = (items[0].get("item") or {}).get("id")
    leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
    active = [l for l in leads if not l.get("is_archived")]
    # DEFECT 2 FIX - lead-per-campaign. Taking active[0] sent one person's EMAIL sends to their
    # LinkedIn lead (512995). Order: campaign field match -> title prefix (Make leaves the campaign
    # field EMPTY, so the prefix is the only signal on Make-created leads) -> single active lead.
    # Never guess when several remain: an unrouted send is recoverable, a misrouted one is a lie on
    # someone's card.
    F_CAMP = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
    by_field = [l for l in active if str(l.get(F_CAMP) or "") == cname]
    by_title = [l for l in active if str(l.get("title") or "").startswith(f"{a.campaign} - ")]
    if by_field:
        lead_id = by_field[0].get("id")
    elif by_title:
        lead_id = by_title[0].get("id")
    elif len(active) == 1:
        lead_id = active[0].get("id")
    else:
        lead_id = None
        if active:
            unroutable.append({"email": email, "sends": len(evs), "person_id": pid,
                               "why": f"ambiguous: {len(active)} active leads, none matching "
                                      f"campaign {a.campaign}"})
            continue
    try:
        kind, frag = activity_target(pd, pid, lead_id)
    except DealGuardBlocked as e:
        unroutable.append({"email": email, "why": f"deal state unknown: {e}", "sends": len(evs)})
        continue
    if kind == "none":
        unroutable.append({"email": email, "why": "person has no lead and no open deal",
                           "sends": len(evs), "person_id": pid})
        continue
    # existing activities on this target, to make the backfill idempotent by key
    q = f"lead_id={lead_id}" if kind == "lead" else f"deal_id={frag['deal_id']}"
    acts = (pd(f"/api/v2/activities?{q}&limit=100") or {}).get("data") or []
    seen_keys = set()
    for act in acts:
        m = re.search(r"\[key:([^\]]+)\]", str(act.get("note") or ""))
        if m:
            seen_keys.add(m.group(1))
    planned_keys = set()
    for ev in evs:
        # HTML-SAFE: Pipedrive's note field is HTML. message_id carries RFC angle brackets
        # (<id@domain>) and the note parser strips them as an unknown tag - which silently emptied
        # all 983 keys once already. Strip them here, never write raw angle brackets into a note.
        key = f"O|SL|{str(ev['message_id']).strip().lstrip('<').rstrip('>')}"
        if key in planned_keys:
            # byte-identical duplicate row in the provider feed - one send, one activity
            continue
        planned_keys.add(key)
        if key in seen_keys:
            already += 1
            continue
        note = (f"→ SENT via campaign {cname}\n"
                f"from {ev['from']}  ·  step {ev['seq']}  ·  {ev['time']}\n\n"
                f"Subject: {ev['subject']}\n\n{ev['body'][:6000]}\n\n[key:{key}]")
        body = {"subject": f"→ Sent — {cname}", "type": "email", "done": True,
                "owner_id": OWNER, "note": note,
                "due_date": str(ev["time"])[:10]}
        body.update(frag)
        plan.append({"email": email, "key": key, "kind": kind, "body": body})
    if i % 40 == 0:
        print(f"  ...resolved {i}/{len(sends)}  planned={len(plan)} unroutable={len(unroutable)}")

print(f"\nPLANNED activities: {len(plan)}")
print(f"  already present (key found): {already}")
print(f"  unroutable leads: {len(unroutable)} ({sum(u['sends'] for u in unroutable)} sends)")
by_kind = defaultdict(int)
for p in plan:
    by_kind[p["kind"]] += 1
print(f"  by target: {dict(by_kind)}")
for u in unroutable[:5]:
    print(f"    UNROUTABLE {u['email']} — {u['why']}")

print("\n--- EXAMPLE ROWS (what lands on a card) ---")
for p in plan[:4]:
    print(f"\n  {p['email']}  [{p['kind']}]")
    print(f"    subject : {p['body']['subject']}")
    print(f"    due     : {p['body']['due_date']}")
    print(f"    note    :")
    for line in p["body"]["note"].splitlines()[:7]:
        print(f"      {line[:96]}")

json.dump({"campaign": a.campaign, "campaign_name": cname, "plan": plan,
           "unroutable": unroutable, "already": already},
          open(os.path.join(HERE, f"outbound_backfill_plan_{a.campaign}.json"), "w",
               encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"\nartifact: outbound_backfill_plan_{a.campaign}.json")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
    sys.exit(0)

print("\n=== WRITING ===")
ok = fail = 0
for i, p in enumerate(plan, 1):
    r = pd("/api/v2/activities", "POST", p["body"])
    if r.get("__err"):
        fail += 1
        if fail <= 3:
            print(f"  FAIL {p['email']}: {r['__err'][:120]}")
    else:
        ok += 1
    if i % 50 == 0:
        print(f"  ...{i}/{len(plan)}  ok={ok} fail={fail}")
        time.sleep(1)
print(f"\nWROTE {ok}   failed {fail}")
