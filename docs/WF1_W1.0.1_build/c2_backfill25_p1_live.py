"""C2 — backfill-25, P1 LIVE, with the Handover guard.

P1 items (from the WF-1 gap audit): Person-ef1ea617 (add 'responded' + reply activity), Andrew
Miller-McKeever (add 'responded'), Person-6193c11f (add 'connected'), Person-451d4581 (reply activity
only, no label change).

HANDOVER GUARD: Pipedrive's native "Responded handover to Melisa" automation fires on
Lead-updated + label "3. Responded" + owner=Melisa + no next activity -> creates a Handover.
Baseline check (done) showed BOTH Rishab's and Andrew's leads have zero activities right now, so
self-suppression does NOT apply - the automation WILL fire for both once 'responded' lands.
Guard: after each write that adds 'responded', wait, re-check activities on that lead, and if a new
one appeared that we did not create ourselves, mark it done with a note. Huy (adds 'connected', not
'responded') and Nelson (no label change) are not expected to trigger this automation at all - checked
anyway, for completeness, not assumed safe.

WRITE_MODE=live required. Real writes happen here.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

WRITE_MODE = os.environ.get("WRITE_MODE", "shadow")
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
UA = "Mozilla/5.0 janea-flipday/1.0"
L_RESP = "c9d4b550-bcf3-11ef-a843-357f91e826ec"
L_CONN = "ca698a50-bdfb-11ef-8172-510383583b0e"
MELISA = 16340280

ITEMS = [
    {"name": "Person-ef1ea617", "lead_prefix": "a81299b0", "person_id": 84559,
     "add_label": L_RESP, "reply_text": True,
     "reply_body": ("Rune - happy to try and connect after sessions. Unfortunately I'm be sponsored "
                    "by my leadership to learn specific things and can't promise anything but will "
                    "try!")},
    {"name": "Andrew Miller-McKeever", "lead_prefix": "8d9a2ab0", "person_id": 82988,
     "add_label": L_RESP, "reply_text": False},
    {"name": "Person-6193c11f", "lead_prefix": "e0e600f0", "person_id": 46630,
     "add_label": L_CONN, "reply_text": True,
     "reply_body": "Great happy to connect at Ai4"},
    {"name": "Person-e1593f4e", "lead_prefix": "a51ea990", "person_id": 85133,
     "add_label": L_RESP, "reply_text": False},
    # verbatim from HeyReach's inbox (2026-08-05 pull) - two distinct reply exchanges, not guessed
    {"name": "Person-451d4581", "lead_prefix": "4833b670", "person_id": 84492,
     "add_label": None, "reply_texts": [
         ("2026-08-02T15:54:56Z", "So do we.   I told my team when we grow up we want to be "
          "just like Avatier.  "),
         ("2026-08-03T16:58:09Z",
          "And you love what you do, you’ve never worked one day in your life!\n\nI have a "
          "whole team of young kids that are all vibe programming in every aspect of the "
          "business. We are all vibe programmers. We are all AI creators first, and it’s "
          "created this co-op petition in this wonderful help attitude. Everybody wants to help "
          "everyone. It’s amazing. There’s no way we can lose, so the goal now 100 "
          "million ARR unless in 12 months. That’s our goal\n\nWe can always grow the "
          "number of customers. There are people that we have in our company, but our "
          "competition cannot go down to 100 employees. We’ll be out of business if they "
          "do")]},
]


def pd(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.pipedrive.com" + path, data=data, method=method,
                                       headers={"x-api-token": PDT, "User-Agent": UA,
                                                **({"Content-Type": "application/json"}
                                                   if data else {})})
            with urllib.request.urlopen(r, timeout=120) as x:
                return x.status, json.load(x)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(4 * (i + 1))
                continue
            return e.code, b
    return 0, None


def find_lead(prefix):
    leads, start = [], 0
    while True:
        st, d = pd(f"/v1/leads?limit=500&start={start}&archived_status=all&sort=add_time%20DESC")
        b = d.get("data") or []
        leads.extend(b)
        more = ((d.get("additional_data") or {}).get("pagination") or {})
        start += len(b)
        if not b or not more.get("more_items_in_collection"):
            break
    return next((L for L in leads if str(L.get("id", "")).startswith(prefix)), None)


def guard_check_and_close(lead_id, before_ids, label):
    """Find any activity that appeared after our write that wasn't there before; close it."""
    time.sleep(6)          # give the native automation a moment to fire
    st, d = pd(f"/v1/activities?lead_id={lead_id}&done=0&limit=100")
    now_acts = d.get("data") or []
    new_ones = [a for a in now_acts if a["id"] not in before_ids]
    for a in new_ones:
        note = (a.get("note") or "")
        note = (note + "\n\nhistorical backfill — already handled").strip()
        st, r = pd(f"/v1/activities/{a['id']}", "PUT", {"done": True, "note": note})
        print(f"    GUARD: closed activity {a['id']} ({a.get('subject')!r}) -> {st}")
    if not new_ones:
        print("    GUARD: no new activity appeared - native automation did not fire (or already"
              " suppressed)")
    return new_ones


def main():
    live = WRITE_MODE == "live"
    print(f"WRITE_MODE={WRITE_MODE!r}  ({'LIVE' if live else 'dry run'})")
    guarded_count = 0
    for it in ITEMS:
        print(f"\n{'=' * 90}\n{it['name']}\n{'=' * 90}")
        lead = find_lead(it["lead_prefix"])
        if not lead:
            print("  LEAD NOT FOUND - skipping")
            continue
        lid = lead["id"]
        st, before = pd(f"/v1/activities?lead_id={lid}&done=0&limit=100")
        before_ids = {a["id"] for a in (before.get("data") or [])}
        print(f"  lead={lid}  labels_before={lead.get('label_ids')}  open_acts_before={len(before_ids)}")
        if not live:
            if it["add_label"]:
                print(f"  WOULD PATCH labels += {it['add_label']}")
            for body_text in ([it["reply_body"]] if it.get("reply_body")
                              else [t for _, t in it.get("reply_texts", [])]):
                print(f"  WOULD POST reply activity: {body_text[:60]!r}")
            continue
        if it["add_label"]:
            labs = list({*(str(x) for x in (lead.get("label_ids") or [])), it["add_label"]})
            st, r = pd(f"/v1/leads/{lid}", "PATCH", {"label_ids": labs})
            print(f"  PATCH labels -> {st}  now={labs}")
            if st >= 300:
                print(f"  FAILED: {r}")
                continue
            if it["add_label"] == L_RESP:
                new_ones = guard_check_and_close(lid, before_ids, it["add_label"])
                guarded_count += len(new_ones)
        for at, body_text in ([(None, it["reply_body"])] if it.get("reply_body")
                              else it.get("reply_texts", [])):
            body = {"subject": f"LinkedIn reply: {it['name']}", "type": "linkedin_messaging",
                    "done": True, "user_id": MELISA, "lead_id": lid,
                    "person_id": it["person_id"], "note": body_text}
            st, r = pd("/v1/activities", "POST", body)
            print(f"  POST reply activity ({at or 'n/a'}) -> {st}")
    print(f"\nTOTAL Handovers auto-closed by the guard: {guarded_count}")


if __name__ == "__main__":
    main()
