#!/usr/bin/env python3
"""REPAIR — Person-7267ff83's 'Interested' reply, which the ambiguous-suppression ate.

Her reply of 2026-08-13 16:37Z currently has: no alert, no forward, no lead, no label, no activity.
Person 69696 exists with 0 leads.

WHY DIRECT WRITES AND NOT A WEBHOOK REPLAY: a replay needs WF-2's staticData dedupe claim released
first, and that store is the one that has already cost us 113 claims to lost-update races. A replay
would also classify third_party and so still not alert. Direct writes in the London-backfill shape,
using WF-2's OWN constants and body shapes, so the result is what WF-2 would have written.

Every body below is copied from the live node it imitates:
  Body Lead Create       title = [campaign_id, campaign_name, full_name].join(' - ')
  Body Lead Labels Union reply => cold + connected + responded, as a UNION
  Body Reply Activity    subject 'Email reply — <campaign>', type email, done, note = subj + body

Dry-run by default. --live writes. The team alert is posted separately, after these succeed, so it
can link the real lead.
"""
import argparse, html, json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

PERSON = 69696
ORG = 13411
CAMPAIGN_ID = 3085711
CAMPAIGN = "[Events Visiting] HumanX 2026 - Valids"
FULL_NAME = "Person-7267ff83"
LEAD_EMAIL = "pii-eb7de9be@example.invalid"
WROTE = "Person-36e26da4 <pii-10d2dcec@example.invalid>"
SUBJECT = "Meet at HumanX in SF?"
REPLY_DATE = "2026-08-13"
OWNER = 16340280
CHANNEL = 578
OPP_TYPE = 480
L_COLD = "a6d359b0-6a45-11ed-ab46-5b95b19fcb18"
L_CONNECTED = "ca698a50-bdfb-11ef-8172-510383583b0e"
L_RESPONDED = "c9d4b550-bcf3-11ef-a843-357f91e826"  # completed below from CONFIG
F_LEAD_CAMPAIGN = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
F_LEAD_OPP = "c7e3057693b6f16fbe40bba2c439d38f8ceb1d84"

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
a = ap.parse_args()


def n8n(p, attempt=0):
    # exec 16265 carries a 208 KB HTML body; this read has already timed out once. Retry the READS
    # freely - they are idempotent. The WRITES below are deliberately NOT retried.
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if attempt < 4:
            print(f"   read retry {attempt + 1} ({str(e)[:60]})")
            time.sleep(8)
            return n8n(p, attempt + 1)
        raise


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


# the responded label id, read from CONFIG rather than retyped from a truncated print
blob = json.dumps(n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv"))
m = re.search(r'\\"responded\\":\s*\\"([0-9a-f\-]+)\\"', blob) or \
    re.search(r'"responded":\s*"([0-9a-f\-]+)"', blob)
if not m:
    raise SystemExit("could not read the responded label id from CONFIG - refusing to guess")
L_RESPONDED = m.group(1)
print(f"responded label id (from CONFIG): {L_RESPONDED}")

# the reply text, from the original webhook payload
det = n8n("/api/v1/executions/16265?includeData=true")
rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
raw = rd["Webhook"][0]["data"]["main"][0][0]["json"]
raw = raw.get("body", raw)
htmlbody = str(raw.get("reply_body") or "")
txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", htmlbody)
txt = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", txt)
txt = re.sub(r"(?s)<[^>]+>", "", txt)
txt = html.unescape(txt)
txt = re.sub(r"[ \t\xa0]+", " ", txt)
txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
# the quoted trail is most of the 208k; keep only the new part. The attribution line is LOCALISED -
# this thread's is French ('Le ... a écrit :'), so an English-only pattern leaves the whole quote in.
QUOTE = re.compile(
    r"\nOn .{0,120}wrote\s*:"           # en
    r"|\nLe .{0,120}a écrit\s*:"   # fr
    r"|\nAm .{0,120}schrieb\s*:"        # de
    r"|\nEl .{0,120}escribió\s*:"  # es
    r"|\n-{2,}\s*(Forwarded|Original)"
    r"|\nFrom: ", re.I)
cut = QUOTE.split(txt)[0].strip()
reply_text = (cut or txt)[:8000]
print(f"reply text extracted: {len(reply_text)} chars (from {len(htmlbody)} of HTML)")
print("-" * 70)
print(reply_text[:600])
print("-" * 70)

# ---- pre-flight: never create a duplicate. Campaign field AND title prefix (Make leaves the
# campaign field empty, so the field check alone misses Make-created leads).
existing = (pd(f"/v1/leads?limit=100&person_id={PERSON}") or {}).get("data") or []
title = " - ".join([str(CAMPAIGN_ID), CAMPAIGN, FULL_NAME])
dupes = [l for l in existing
         if str(l.get(F_LEAD_CAMPAIGN) or "") == CAMPAIGN
         or str(l.get("title") or "").startswith(f"{CAMPAIGN_ID} - ")]
print(f"\npre-flight: person {PERSON} has {len(existing)} leads; "
      f"matching this campaign: {len(dupes)}")
for l in dupes:
    print(f"   EXISTS {l.get('id')} {l.get('title')!r}")
if dupes:
    raise SystemExit("a lead for this campaign already exists - stopping, this repair is done")

note = "\n\n".join(filter(None, [
    f"⚠️ Replied by {WROTE} on {FULL_NAME}'s thread — third party, same domain. "
    f"The lead below is the campaign lead; the text was written by the colleague named above.",
    f"Subject: {SUBJECT}",
    reply_text,
]))

lead_body = {"title": title, "person_id": PERSON, "owner_id": OWNER,
             "label_ids": [L_COLD], "channel": CHANNEL, "organization_id": ORG,
             F_LEAD_CAMPAIGN: CAMPAIGN, F_LEAD_OPP: OPP_TYPE}
print("\n=== PLANNED WRITES ===")
print("1. POST /v1/leads")
print(json.dumps(lead_body, indent=2, ensure_ascii=False)[:700])
print(f"\n2. PATCH /v1/leads/<new>  label_ids = [cold, connected, responded]")
print(f"\n3. POST /api/v2/activities  subject='Email reply — {CAMPAIGN}' type=email done=true "
      f"due_date={REPLY_DATE} note={len(note)} chars")
print(f"\n   note head: {note[:220]!r}")

if not a.live:
    print("\n--live not given: NOTHING WRITTEN.")
    raise SystemExit(0)

print("\n=== WRITING ===")
r1 = pd("/v1/leads", "POST", lead_body)
if r1.get("__err") or not (r1.get("data") or {}).get("id"):
    raise SystemExit(f"lead create FAILED: {r1.get('__err') or json.dumps(r1)[:300]}")
LEAD = r1["data"]["id"]
print(f"  lead created: {LEAD}")

r2 = pd(f"/v1/leads/{LEAD}", "PATCH", {"label_ids": [L_COLD, L_CONNECTED, L_RESPONDED]})
labels = ((r2.get("data") or {}).get("label_ids")) or []
print(f"  labels: {len(labels)} -> {labels}"
      f"{'  <-- responded present' if L_RESPONDED in labels else '  <-- RESPONDED MISSING'}")

act = {"subject": f"Email reply — {CAMPAIGN}", "type": "email", "done": True,
       "owner_id": OWNER, "lead_id": LEAD, "note": note, "due_date": REPLY_DATE}
r3 = pd("/api/v2/activities", "POST", act)
aid = ((r3.get("data") or {}) or {}).get("id")
print(f"  activity: {aid}{'  ERR ' + str(r3.get('__err')) if r3.get('__err') else ''}")

# read back - a POST returning ok is not evidence the row is there
back = (pd(f"/v1/leads?limit=50&person_id={PERSON}") or {}).get("data") or []
acts = (pd(f"/api/v2/activities?lead_id={LEAD}&limit=10") or {}).get("data") or []
print(f"\n  READBACK: person {PERSON} leads={len(back)}  activities on lead={len(acts)}")
for l in back:
    print(f"     {l.get('id')} {str(l.get('title'))[:60]!r} labels={len(l.get('label_ids') or [])}")
print(f"\nLEAD_ID={LEAD}")
print(f"LEAD_URL=https://janeasystems.pipedrive.com/leads/inbox/{LEAD}")
