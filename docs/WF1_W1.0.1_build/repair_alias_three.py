#!/usr/bin/env python3
"""#27 item 2 — repair the three ALIAS replies of 2026-07-31 (Conrad / Joseph / Rachel).

Each is the campaign lead replying from a second address at the same domain. The old Normalize
adopted the SENDER as the lead, so person search missed, no lead resolved, and the real lead got no
label and no activity. All three leads exist, carry 1 label, no 'responded', and zero activities -
so this repair is additive and idempotent.

Reply text comes from Smartlead's own history. Traps this code is written around:
  * leads-statistics rows key on `to` / `lead_id` - there is NO lead_email or reply_time field
  * the reply lives inside history[]; history[].time carries BOTH ISO-8601 and RFC-2822 forms
  * limit is capped at 100 and the default ordering is the OLDEST page - so page until hasMore
    is false rather than trusting the first page
"""
import argparse, html, json, os, re, ssl, urllib.parse, urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
OWNER = 16340280

WHO = [
    ("Person-65862a8f", 83499, "e023da50-852b-11f1-b209-99679032709a",
     "pii-6e4e8b43@example.invalid", "pii-9efda044@example.invalid", 3686184),
    ("Person-9c782f71", 83604, "ccaa9140-8534-11f1-b209-99679032709a",
     "pii-1011b46b@example.invalid", "pii-e56d5459@example.invalid", 3686181),
    ("Person-1a93b995", 83661, "406ca200-8538-11f1-919d-e9901f5fca95",
     "pii-399e6070@example.invalid", "pii-3d090878@example.invalid", 3686184),
]
CAMPAIGN_NAMES = {3686181: "[Events Visiting] AI4 2026 - Mario - Valids",
                  3686184: "[Events Visiting] AI4 2026 - Mario - Catch-alls"}

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
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
        return {"__err": f"HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}"}


def sl(path, **q):
    q["api_key"] = SL
    url = f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
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


QUOTE = re.compile(r"\nOn .{0,120}wrote\s*:|\nLe .{0,120}a écrit\s*:"
                   r"|\nAm .{0,120}schrieb\s*:|\nEl .{0,120}escribió\s*:"
                   r"|\n-{2,}\s*(Forwarded|Original)|\nFrom: ", re.I)


def find_reply(campaign_id, lead_email):
    """Page until hasMore is false - the default page is the OLDEST, never trust page 1."""
    offset, pages = 0, 0
    while pages < 40:
        r = sl(f"/campaigns/{campaign_id}/leads-statistics", limit=100, offset=offset)
        rows = (r or {}).get("data") or []
        for row in rows:
            if str(row.get("to") or "").strip().lower() != lead_email.lower():
                continue
            hist = row.get("history") or []
            reps = [h for h in hist
                    if "repl" in str(h.get("type") or h.get("event_type") or "").lower()
                    or h.get("is_reply") is True]
            return row, reps, pages
        if not (r or {}).get("hasMore"):
            return None, [], pages
        offset += 100
        pages += 1
    return None, [], pages


for name, pid, lead_id, lead_email, alias, cid in WHO:
    print(f"=== {name} ===")
    row, reps, pages = find_reply(cid, lead_email)
    if not row:
        print(f"  NOT FOUND in campaign {cid} after {pages+1} page(s) - skipping, will not "
              f"invent an activity body")
        continue
    print(f"  found on page {pages} · lead_id={row.get('lead_id')} · history={len(row.get('history') or [])} "
          f"· reply entries={len(reps)}")
    if not reps:
        h = row.get("history") or []
        print(f"  history types present: {sorted({str(x.get('type') or x.get('event_type')) for x in h})}")
        print("  no reply entry identified - SKIPPING rather than guessing")
        continue
    rep = reps[-1]
    body = strip_html(rep.get("email_body") or rep.get("body") or rep.get("message") or "")
    body = QUOTE.split(body)[0].strip()[:8000]
    when = str(rep.get("time") or rep.get("created_at") or "")
    iso = when[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", when) else None
    subj = rep.get("subject") or ""
    print(f"  reply time={when[:40]!r} -> due_date={iso}")
    print(f"  subject={str(subj)[:60]!r}")
    print(f"  body ({len(body)} chars): {body[:220]!r}")

    # These bodies are OUT-OF-OFFICE autoresponders, not replies from a human who read anything.
    # The queued spec said '3. Responded + reply activity', but that was written before anyone read
    # the text. The OOO gate exists precisely to keep an autoresponder from marking a lead as having
    # responded: no alert, no forward, NO responded label - activity still written. Honouring the
    # spec here would have manufactured three false warm signals in Melisa's queue.
    OOO = re.compile(r"out of (the )?office|will return on|limited email access|"
                     r"i am currently out|respond to your message when i return", re.I)
    is_ooo = bool(OOO.search(body))
    cur = (pd(f"/v1/leads/{lead_id}") or {}).get("data") or {}
    existing = list(cur.get("label_ids") or [])
    union = existing[:]
    if not is_ooo:
        for x in (L_COLD, L_CONNECTED, L_RESPONDED):
            if x not in union:
                union.append(x)
    note = "\n\n".join(filter(None, [
        ("AUTO-REPLY (out of office) received from " + alias + " — the campaign lead is "
         + lead_email + ". No 'responded' label: nobody has actually read the message."
         if is_ooo else
         f"Replied from {alias} — the same person under a second address at the same domain "
         f"(alias). The campaign lead is {lead_email}."),
        (f"Subject: {subj}" if subj else None), body,
        "— Backfilled 2026-08-14. WF-2 originally adopted the SENDER as the lead, so this never "
        "reached the campaign lead's record."]))
    act = {"subject": (("Auto-reply (OOO) — " if is_ooo else "Email reply — ")
                       + str(CAMPAIGN_NAMES.get(cid, cid))),
           "type": "email", "done": True, "owner_id": OWNER, "lead_id": lead_id, "note": note}
    if iso:
        act["due_date"] = iso
    print(f"  CLASSIFIED: {'OUT-OF-OFFICE auto-reply' if is_ooo else 'genuine reply'}")
    print(f"  PLAN: labels {len(existing)} -> {len(union)}"
          f"{'  (NO responded - OOO)' if is_ooo else '  (responded added)'}, "
          f"activity note {len(note)} chars")

    if not a.live:
        print("  (dry-run)\n")
        continue

    got = existing
    if union != existing:
        r1 = pd(f"/v1/leads/{lead_id}", "PATCH", {"label_ids": union})
        got = ((r1.get("data") or {}).get("label_ids")) or []
        if r1.get("__err") or L_RESPONDED not in got:
            print(f"  LABEL FAILED: {r1.get('__err') or got} - skipping activity\n")
            continue
    else:
        print("  labels unchanged by design (OOO)")
    r2 = pd("/api/v2/activities", "POST", act)
    if r2.get("__err"):
        print(f"  ACTIVITY FAILED: {r2['__err']}\n")
        continue
    back = (pd(f"/api/v2/activities?lead_id={lead_id}&limit=10") or {}).get("data") or []
    print(f"  WROTE labels={len(got)} responded=yes · activity={(r2.get('data') or {}).get('id')} "
          f"· readback activities={len(back)}\n")
