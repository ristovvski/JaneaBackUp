#!/usr/bin/env python3
"""CAMPAIGN-ORIGIN GATE — WF-1 M7 Alert Gate. Personal chats stop announcing.

Melisa, verbatim: "We shouldn't get notifications about personal chats (lead not from campaigns)".

Person-b0fb1597 (26 Aug) and Person-7cb57cf4 (27 Aug) were BOTH resolved correctly — `M7 Person Search
URL` returned items=1 in each case (85761, 85519). Neither was a match miss and neither created a
lead. Both were replies inside a MANUAL HeyReach inbox thread belonging to Noah, where
`campaign = null`. The gate already labels this: the alert key ends `|nocamp`.

14-day census of #lead-processing: 11 alerts delivered, 5 with no campaign — **45% of the channel**
(Josh, Person-c1b92fbb, Person-9979a87c, Person-b0fb1597, Person-8d8b92ff).

WHAT THIS CHANGES: only the ALERT branch. Labels (`M7 Labels Compute` -> `M7 Lead Patch`) and the
reply activity (`M7 Reply Activity`) hang off other branches and are untouched, so a personal chat
is still recorded silently — outbound logging continues exactly as before. The system logs; it just
stops announcing.

WHY NOT THE "known-person" GATE as specified: every one of the 6 legitimate campaign alerts in the
same window ALSO resolved a person — resolving one is how the alert gets its lead link. A gate on
"person is known" suppresses 11 of 11 and deletes the feature. Ken and Josh were both *known*; being
known is not what made them noise. The campaign-origin gate is the one that separates the classes,
and it is sufficient for both reported cases.

Placement is deliberate: BEFORE the `!key` fail-open, so a manual thread with no identity is silent
too (that fail-open exists to protect campaign replies, not personal chats).
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1 = "2jdjKM2NJr473GdA"

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, att=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF1}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["M7 Alert Gate"]["parameters"]["jsCode"]
if "__manual_thread" in js:
    sys.exit("gate already present")

OLD = """let should, reason;
if (!key) {"""
if OLD not in js:
    sys.exit("M7 Alert Gate decision block not found verbatim - refusing to patch blind")
NEW = """// CAMPAIGN-ORIGIN GATE (Melisa, 2026-08-27): "We shouldn't get notifications about personal chats
// (lead not from campaigns)". A HeyReach inbox thread with no campaign is the exec's own
// conversation. Labels and the reply activity still run on their own branches - this suppresses the
// ANNOUNCEMENT only. Placed BEFORE the !key fail-open on purpose: that fail-open protects campaign
// replies from being lost, and must not resurrect a personal chat that has no identity either.
const __manual_thread = !(n.campaign && (n.campaign.id ?? n.campaign.name));

let should, reason;
if (__manual_thread) {
  should = false; reason = 'manual_conversation';
} else if (!key) {"""
js2 = js.replace(OLD, NEW, 1)
js2 = js2.replace("return [{ json: { ...b, __alert_key: key, __should_alert: should,",
                  "return [{ json: { ...b, __alert_key: key, __should_alert: should,\n"
                  "                  __manual_thread,", 1)
N["M7 Alert Gate"]["parameters"]["jsCode"] = js2

print("--- statics: the four cases ---")
ok = True


def run(campaign, lead_id, person_id, reg):
    body = js2
    src = f"""
const CFG = {{}};
const NORM = {{ campaign: {json.dumps(campaign)},
                lead: {{ member_id: null, public_id: null, li_url: null }} }};
const B = {{ lead_id: {json.dumps(lead_id)}, person_id: {json.dumps(person_id)} }};
const $json = B;
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  throw new Error('absent ' + nm);
}};
const SD = {{ __alerted_v1: {json.dumps(reg)} }};
const $getWorkflowStaticData = () => SD;
const OUT = (() => {{
{body}
}})();
const j = OUT[0].json;
console.log(JSON.stringify({{ should: j.__should_alert, reason: j.__alert_reason,
                              key: j.__alert_key, manual: j.__manual_thread }}));
"""
    tmp = os.path.join(HERE, "_mg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:280]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


CAMP = {"id": 512995, "name": "[Events Visiting] [Ai4 2026] - Mario - LinkedIn"}
CASES = [
    ("manual chat + UNKNOWN person -> SILENCE", None, None, None, {}, False, "manual_conversation"),
    ("manual chat + KNOWN person (Ken/Josh) -> SILENCE (+ note still written)",
     None, "L1", 85519, {}, False, "manual_conversation"),
    ("campaign reply, first -> ALERT as today", CAMP, "L1", 85519, {}, True, "first_alert"),
    ("campaign reply, already delivered -> suppressed as today",
     CAMP, "L1", 85519, {"LL1|512995": "2026-08-20T00:00:00Z"}, False, "already_delivered"),
    ("campaign reply, NO identity -> still fails open (unchanged)",
     CAMP, None, None, {}, True, "no_identity"),
]
for label, camp, lid, pid, reg, want_should, want_reason in CASES:
    got, err = run(camp, lid, pid, reg)
    if err:
        print(f"  [FAIL] {label}\n         {err}")
        ok = False
        continue
    good = got["should"] is want_should and got["reason"] == want_reason
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         should={got['should']} reason={got['reason']!r} "
          f"manual={got['manual']} key={got['key']!r}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN (Nik's word gates this).")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf1_backup_before_manualgate_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF1}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF1}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "__manual_thread" not in AN["M7 Alert Gate"]["parameters"]["jsCode"]:
    problems.append("gate not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-1 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
