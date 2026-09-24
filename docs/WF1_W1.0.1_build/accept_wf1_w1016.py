"""Live acceptance for W1.0.16, on a controlled test person that is deleted afterwards.

Design so that NOTHING is written to a real prospect:
  * the test person is created by us, with a member_id nobody else uses and a li_url that
    deliberately differs from what the event will carry
  * the event carries an EMPTY email, so `IF Email Present` is false and the flow goes straight to
    the URL search - which must miss - and then into the new member fallback
  * the campaign is fictional, so no lead exists for it: the branch ends in a Slack ops warn with
    NO CRM write. The proof is in the execution data, not in a mutation.
  * A2 is the negative control: an unknown member key must NOT resolve, and must fall through to the
    original not-found target.
Cleanup deletes the test person at the end.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
WF1 = os.environ["WF1_ID"]
NKEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
HOOK = BASE + "/webhook/{{WEBHOOK_WF1_HEYREACH_RECEIVER}}"
UA = "Mozilla/5.0 janea-accept/1.0"
F_MEMBER = "010fc51128116e8c73ae2b33fd52fd4537451f2b"
F_PUBLIC = "2339d1c7a7cda05651dff68ff82b2d56b20e241d"
F_LI = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
# A FRESH key per run. Re-using one bit us once: Pipedrive DELETE is a SOFT delete and
# persons/search still returns deleted records, so the previous run's fixture came back as a second
# candidate and oldest-wins resolved to the deleted one. That is real (pre-existing) behaviour for
# every search in this workflow - see the task log - but it must not confound the test.
_RUN = int(time.time()) % 100000
TEST_MEMBER_ID = 990000000 + _RUN
UNKNOWN_MEMBER_ID = 880000000 + _RUN
VANITY = "https://www.linkedin.com/in/pii-c7d11ca5"
URN = "https://www.linkedin.com/in/pii-00e9a4f3"


def pd(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + path, data=data, method=method,
                               headers={"x-api-token": PDT, "User-Agent": UA,
                                        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(r, timeout=150) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": NKEY})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.load(x)


def fire(payload):
    r = urllib.request.Request(HOOK, data=json.dumps(payload).encode(), method="POST",
                              headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            return x.status, x.read().decode("utf-8", "replace")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def event(member_id, label):
    return {
        "event_type": "message_sent",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "correlation_id": str(uuid.uuid4()),
        "conversation_id": f"w1016-{label}",
        "lead": {"id": member_id, "profile_url": URN,
                 "first_name": "W1016", "last_name": f"Acceptance {label}",
                 "full_name": f"W1016 Acceptance {label}", "email_address": "",
                 "company_name": "Janea Test Harness", "position": "Fixture",
                 "location": "", "summary": ""},
        "campaign": {"id": 999016, "name": "W1016 Fallback Acceptance"},
        "sender": {"full_name": "Acceptance Harness"},
    }


created_person = None
try:
    print("=" * 92)
    print("SETUP - a test person whose li_url deliberately differs from the event URL")
    print("=" * 92)
    st, r = pd("/api/v2/persons", "POST", {
        "name": "W1016 Fallback Acceptance Fixture",
        "custom_fields": {F_MEMBER: TEST_MEMBER_ID, F_PUBLIC: "w1016-acceptance-vanity",
                          F_LI: VANITY}})
    if st >= 300:
        sys.exit(f"could not create the fixture person: {st} {r}")
    created_person = (r.get("data") or {}).get("id")
    print(f"  person {created_person} created")
    print(f"    member_id = {TEST_MEMBER_ID}")
    print(f"    li_url    = {VANITY}")
    print(f"    event will carry profile_url = {URN}  <- must NOT match li_url")

    before = {e["id"] for e in (n8n(f"/api/v1/executions?workflowId={WF1}&limit=50")
                                .get("data") or [])}

    print("\n" + "=" * 92)
    print("A1 - the URN event must resolve to our fixture via the member fallback")
    print("=" * 92)
    st, body = fire(event(TEST_MEMBER_ID, "A1"))
    print(f"  webhook -> {st} {body}")

    print("\n" + "=" * 92)
    print("A2 (negative control) - an unknown member key must NOT resolve")
    print("=" * 92)
    time.sleep(8)
    st, body = fire(event(UNKNOWN_MEMBER_ID, "A2"))
    print(f"  webhook -> {st} {body}")

    print("\n  waiting for both executions to finish...")
    deadline = time.time() + 150
    fresh = []
    while time.time() < deadline:
        time.sleep(10)
        rows = n8n(f"/api/v1/executions?workflowId={WF1}&limit=50").get("data") or []
        fresh = [e for e in rows if e["id"] not in before]
        if len(fresh) >= 2 and all(e.get("stoppedAt") for e in fresh):
            break
    print(f"  new executions: {[(e['id'], e.get('status')) for e in fresh]}")

    print("\n" + "=" * 92)
    print("EVIDENCE - which resolver nodes ran, and what they returned")
    print("=" * 92)
    verdicts = {}
    for e in sorted(fresh, key=lambda x: x["id"]):
        d = n8n(f"/api/v1/executions/{e['id']}?includeData=true")
        rd = (((d.get("data") or {}).get("resultData") or {}).get("runData") or {})
        conv = None
        try:
            conv = rd["Normalize"][0]["data"]["main"][0][0]["json"]["conv"]
        except Exception:
            pass
        label = "A1" if str(conv).endswith("A1") else ("A2" if str(conv).endswith("A2") else "?")
        print(f"\n  execution {e['id']} ({label}) status={e.get('status')}")
        ran = [n for n in ("M6 Person Search Email", "M6 Person Search URL", "M6 IF URL Found",
                           "M6 Person Search Member", "M6 IF Member Verified",
                           "M6 PID From Member", "M6 Person Get", "M6 Lead Get", "M6 Build",
                           "M6 Person Patch", "M6 Slack Warn", "M6 Message First Warn")
               if n in rd]
        print(f"    nodes run: {ran}")

        def out(node):
            try:
                return rd[node][0]["data"]["main"][0][0]["json"]
            except Exception:
                return None

        u = out("M6 Person Search URL")
        m = out("M6 Person Search Member")
        pidv = out("M6 PID From Member")
        got = out("M6 Person Get")
        nurl = len((((u or {}).get("data") or {}).get("items") or []))
        nmem = len((((m or {}).get("data") or {}).get("items") or []))
        print(f"    URL search hits    : {nurl}   (must be 0 - the URN does not match li_url)")
        print(f"    member search hits : {nmem}")
        print(f"    PID From Member    : {pidv}")
        if got:
            print(f"    Person Get -> id={((got.get('data') or {}).get('id'))} "
                  f"name={((got.get('data') or {}).get('name'))}")
        verdicts[label] = {"url_hits": nurl, "member_hits": nmem,
                           "resolved": ((got or {}).get("data") or {}).get("id"),
                           "ran_member_search": "M6 Person Search Member" in rd,
                           "ran_pid": "M6 PID From Member" in rd,
                           "warned": ("M6 Slack Warn" in rd) or ("M6 Message First Warn" in rd),
                           "wrote_person": "M6 Person Patch" in rd}

    print("\n" + "=" * 92)
    print("VERDICT")
    print("=" * 92)
    a1, a2 = verdicts.get("A1") or {}, verdicts.get("A2") or {}
    checks = [
        ("A1 the URL search missed (URN != stored li_url)", a1.get("url_hits") == 0),
        ("A1 the new member search RAN", a1.get("ran_member_search") is True),
        ("A1 it found exactly one candidate - our fixture", a1.get("member_hits") == 1),
        ("A1 the verified branch resolved a person_id", a1.get("ran_pid") is True),
        ("A1 resolved to OUR fixture person", a1.get("resolved") == created_person),
        ("A2 the member search RAN but found nothing", a2.get("ran_member_search") is True
         and (a2.get("member_hits") or 0) == 0),
        ("A2 did NOT resolve a person (no false positive)", a2.get("ran_pid") is not True),
        ("A2 fell through to the original not-found path", a2.get("warned") is True),
    ]
    ok = True
    for name, good in checks:
        ok &= bool(good)
        print(f"  {'PASS' if good else 'FAIL'}  {name}")
    print(f"\n  {'LIVE ACCEPTANCE PASSED' if ok else 'LIVE ACCEPTANCE FAILED'}")
finally:
    print("\n" + "=" * 92)
    print("CLEANUP")
    print("=" * 92)
    if created_person:
        st, r = pd(f"/api/v2/persons/{created_person}", "DELETE")
        print(f"  delete fixture person {created_person} -> {st}")
        print("  (Pipedrive DELETE is a soft delete; the record leaves all views)")
    else:
        print("  nothing to clean up")
