#!/usr/bin/env python3
"""WF-1: a reply with no correspondent message is not a reply. Plus: the alert now quotes it.

WHY. Person-8768306e (President @ Circle) accepted a connection request. HeyReach emitted
`connection_request_accepted` and `message_reply_received` in the SAME millisecond, and the reply's
`recent_messages` carried one correspondent entry with `message: ""` whose creation_time was 1.5 s
after our own connection message. WF-1 alerted #lead-processing, wrote a permanent `reply_dnc`
registry row, set `3. Responded`, and opened a handover task - for a man who said nothing.

TWO CHANGES.

1) `M7 Blank Reply Gate` - an IF between `Switch[3]` (every_message_reply_received) and
   `M7 IF Email Present`. Placed at the BRANCH ENTRY, not in front of one consequence, so a blank
   reply does no person resolution, no lead GET, no alert, no label, no DNC row, no task and no
   activity. The `connection_request_accepted` path (Switch[1] -> M5) already does the CRM work for
   an accept, so nothing is lost.

   ATTACHMENTS AND VOICE NOTES ARE REAL REPLIES. `M7 Build.render()` deliberately renders them as
   '[attachment]' / '[voice note]' rather than as empty, and the gate uses the same rule - a
   blank-text check alone would silently suppress every attachment reply, trading one bug for a
   worse one.

2) `M7 Build` alert_text gains a `Reply:` row, first ~120 chars. This bug survived because the
   alert says only THAT something arrived, never WHAT - 'Person-8768306e (President @ Circle) …
   Open lead' reads identically whether he wrote three paragraphs or nothing at all. M7 Build has
   had `reply_text` all along, complete with an '[empty message]' placeholder: the workflow knew,
   and never said.

Measured population (n8n retention 2026-08-19 -> 09-11, 1,066 executions, 242 reply events):
**2 blank, 1%**, both Heath. Rare - but it cost one prospect a permanent suppression.
"""
import argparse
import copy
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
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
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:200]))
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


def code_only(js):
    return "\n".join(re.sub(r"//.*$", "", l) for l in js.splitlines()
                     if not l.strip().startswith("//"))


wf = n8n("/api/v1/workflows/%s" % WF1)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.setdefault("connections", {})
if "M7 Blank Reply Gate" in N:
    sys.exit("blank-reply gate already present")
for req in ("Switch", "M7 IF Email Present", "M7 Build", "Normalize"):
    if req not in N:
        sys.exit("missing expected node: %s" % req)

# ---- the shared predicate, used by the gate (kept verbatim in both places on purpose)
PRED = r"""
// A reply is real iff the CORRESPONDENT actually said something. Attachments and voice notes count:
// `M7 Build.render()` renders them as '[attachment]' / '[voice note]', not as empty, and a naive
// blank-text test would suppress every one of them - trading Heath's bug for a worse, quieter one.
const __msgs = Array.isArray(n.msgs) ? n.msgs : [];
const __trailing = [];
for (let i = __msgs.length - 1; i >= 0; i--) {
  const m = __msgs[i];
  if (m && m.is_reply === true) __trailing.unshift(m); else break;
}
const __pool = __trailing.length ? __trailing : __msgs.filter(m => m && m.is_reply === true);
const __real = __pool.some(m => {
  const t = (m.message == null ? '' : String(m.message)).trim();
  if (t) return true;
  const mt = String(m.message_type || '').toLowerCase();
  return mt.includes('attach') || mt.includes('voice') || mt.includes('image')
      || mt.includes('video') || mt.includes('media');
});
"""

GATE_EXPR = ("={{ (() => { const n = (() => { try { return $('Normalize').item.json || {}; }"
             " catch (e) { return $json || {}; } })();"
             + PRED.replace("\n", " ") +
             " return __real; })() }}")

SKIPPED = r"""
// Terminal. A blank-body 'reply' is an accept artefact: HeyReach emits connection_request_accepted
// and message_reply_received in the same millisecond, and the correspondent entry carries
// message: ''. The accept branch (Switch[1] -> M5) does the CRM work; this branch does nothing at
// all - deliberately no alert, no label, no DNC row, no task, no activity. Recorded, not silent.
const n = (() => { try { return $('Normalize').item.json || {}; } catch (e) { return $json || {}; } })();
const msgs = Array.isArray(n.msgs) ? n.msgs : [];
return [{ json: {
  __skipped: 'blank_reply_body',
  __event: n.event ?? null,
  __who: (n.lead || {}).full_name ?? null,
  __profile: (n.lead || {}).profile_url ?? null,
  __campaign: (n.campaign && typeof n.campaign === 'object') ? (n.campaign.name ?? n.campaign.id)
                                                            : (n.campaign ?? null),
  __their_messages: msgs.filter(m => m && m.is_reply === true).length,
  __conversation: n.conv ?? null,
  __at: new Date().toISOString()
} }];
"""

GX, GY = N["M7 IF Email Present"]["position"]
wf["nodes"].append({
    "parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 1},
        "conditions": [{"id": "wf1-blankreply", "leftValue": GATE_EXPR, "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}],
        "combinator": "and"}, "options": {}},
    "name": "M7 Blank Reply Gate", "type": "n8n-nodes-base.if", "typeVersion": 2,
    "position": [GX - 200, GY]})
wf["nodes"].append({
    "parameters": {"jsCode": SKIPPED, "mode": "runOnceForAllItems"},
    "name": "M7 Blank Reply Skipped", "type": "n8n-nodes-base.code", "typeVersion": 2,
    "position": [GX - 200, GY + 180]})

# rewire Switch[3] -> gate -> M7 IF Email Present
sw = (C.get("Switch") or {}).get("main") or []
if len(sw) < 4:
    sys.exit("Switch has %d outputs, expected >=4" % len(sw))
tgt = [l for l in (sw[3] or []) if l and l.get("node") == "M7 IF Email Present"]
if not tgt:
    sys.exit("Switch[3] does not feed M7 IF Email Present; refusing to rewire blind")
sw[3] = [l for l in (sw[3] or []) if l.get("node") != "M7 IF Email Present"]
sw[3].append({"node": "M7 Blank Reply Gate", "type": "main", "index": 0})
C["Switch"]["main"] = sw
C["M7 Blank Reply Gate"] = {"main": [
    [{"node": "M7 IF Email Present", "type": "main", "index": 0}],
    [{"node": "M7 Blank Reply Skipped", "type": "main", "index": 0}]]}

# ---- alert body gains the reply excerpt
mb = N["M7 Build"]["parameters"]["jsCode"]
ANCHOR = ("const alert_text = __headline + (__rows.length ? "
          "'\\n*Details:*\\n' + __rows.join('\\n') : '');")
if ANCHOR not in mb:
    sys.exit("M7 Build alert_text line not found verbatim")
NEW = """// WHAT was said, not only THAT something arrived. Person-8768306e's empty reply produced an
// alert indistinguishable from a real one - name, company, LinkedIn, Open lead - because the alert
// never quoted the message. `reply_text` has existed here all along, '[empty message]' placeholder
// and all: the workflow knew and did not say.
const __excerpt = String(reply_text ?? '').replace(/\\s+/g, ' ').trim();
if (__excerpt) {
  __rows.push('Reply: ' + escapeSlack(__excerpt.slice(0, 120))
              + (__excerpt.length > 120 ? '\\u2026' : ''));
}
const alert_text = __headline + (__rows.length ? '\\n*Details:*\\n' + __rows.join('\\n') : '');"""
N["M7 Build"]["parameters"]["jsCode"] = mb.replace(ANCHOR, NEW, 1)
MB_NEW = N["M7 Build"]["parameters"]["jsCode"]

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True


def run(js, harness, pick="OUT"):
    src = harness + "\nlet __e=null,OUT=null;\ntry{OUT=(()=>{\n" + js + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:" + pick + ",err:__e}));\n"
    tmp = os.path.join(HERE, "_bg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    d = json.loads(p.stdout.strip().splitlines()[-1])
    return d, None


OURS = {"creation_time": "2026-09-11T00:34:43.541Z", "is_reply": False,
        "message": "Hi Heath, I noticed you're heading to FinovateFall this week."}
BLANK = {"creation_time": "2026-09-11T00:34:44.07Z", "is_reply": True, "message": ""}
REAL = {"creation_time": "2026-09-11T00:34:44.07Z", "is_reply": True,
        "message": "Hi Noah, good to hear from you! Next week looks good, let's find a slot."}
ATTACH = {"creation_time": "x", "is_reply": True, "message": "", "message_type": "ATTACHMENT"}
VOICE = {"creation_time": "x", "is_reply": True, "message": "  ", "message_type": "voiceNote"}

GATE_JS = ("const n = NORM;" + PRED + " return __real;")

CASES = [
    ("Heath: blank correspondent reply", [OURS, BLANK], False),
    ("real reply", [OURS, REAL], True),
    ("attachment reply is REAL, not suppressed", [OURS, ATTACH], True),
    ("voice note is REAL, not suppressed", [OURS, VOICE], True),
    ("no messages at all", [], False),
    ("only our own outbound", [OURS], False),
    ("blank then a real follow-up", [OURS, BLANK, REAL], True),
]
for label, msgs, want in CASES:
    d, err = run(GATE_JS, "const NORM = %s;" % json.dumps({"msgs": msgs}))
    got = (d or {}).get("out")
    good = (got is want) and not (d or {}).get("err")
    print("  [%s] %-46s -> %s (want %s)" % ("ok " if good else "FAIL", label, got, want))
    ok = ok and good

# --- alert body
PERSON = {"id": 86369, "custom_fields": {}}
LEAD = {"data": [{"id": "987d0600", "is_archived": False, "F_CAMP": "CAMP"}]}
CFG = {"fields": {"stage": "S", "conversation": "CV", "lead_campaign": "F_CAMP"},
       "stageRank": {}, "melisa_user_id": 16340280, "pipedrive_base": "https://pd.example"}


def mb_harness(msgs, reply_msgs=None):
    norm = {"msgs": msgs, "lead": {"full_name": "Person-8768306e", "position": "President",
                                   "company_name": "Circle",
                                   "profile_url": "https://linkedin.com/in/pii-8bd4c12a"},
            "campaign": {"name": "[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn"},
            "sender": {"name": "Noah Keimach"}, "conv": "c1", "is_inmail": False}
    return ("const CFG=%s, NORM=%s, PERSON=%s, LEADR=%s;\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM"
            " : nm==='M7 Person Get'?{data:PERSON} : nm==='M7 Lead Get'?LEADR : {} } });\n"
            % (json.dumps(CFG), json.dumps(norm), json.dumps(PERSON), json.dumps(LEAD)))


LONG = {"creation_time": "x", "is_reply": True, "message": "y" * 400}
for label, msgs, check in (
        ("alert quotes a real reply", [OURS, REAL],
         lambda t: "Reply: Hi Noah, good to hear from you!" in t),
        ("excerpt truncates at 120 with an ellipsis", [OURS, LONG],
         lambda t: ("Reply: " + "y" * 120 + "…") in t),
        ("attachment shows its placeholder", [OURS, ATTACH],
         lambda t: "Reply: [attachment]" in t),
        ("blank shows the empty-message placeholder", [OURS, BLANK],
         lambda t: "Reply: [empty message]" in t)):
    d, err = run(MB_NEW, mb_harness(msgs), "OUT.json.alert_text")
    txt = (d or {}).get("out") or ""
    good = bool(txt) and check(txt) and not (d or {}).get("err")
    print("  [%s] %-46s %r" % ("ok " if good else "FAIL", label, str(txt)[-90:]))
    if err:
        print("        node error: %s" % err)
    ok = ok and good

# non-vacuity: the OLD M7 Build never mentions the reply
d, err = run(mb, mb_harness([OURS, REAL]), "OUT.json.alert_text")
old = (d or {}).get("out") or ""
good = bool(old) and "Reply:" not in old
print("  [%s] %-46s (old alert carried no reply text)" % ("ok " if good else "FAIL",
                                                          "non-vacuity: old alert body"))
ok = ok and good

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (12)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "wf1_backup_before_blank_gate_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: wf1_backup_before_blank_gate_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % WF1, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % WF1)
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in ("M7 Blank Reply Gate", "M7 Blank Reply Skipped"):
    if nm not in AN:
        problems.append("%s missing" % nm)
sw3 = [l["node"] for l in (((AC.get("Switch") or {}).get("main") or [[]]*4)[3] or [])]
if sw3 != ["M7 Blank Reply Gate"]:
    problems.append("Switch[3] -> %s (expected the gate only)" % sw3)
g = [[l["node"] for l in (b or [])] for b in ((AC.get("M7 Blank Reply Gate") or {}).get("main") or [])]
if g != [["M7 IF Email Present"], ["M7 Blank Reply Skipped"]]:
    problems.append("gate outputs wired as %s" % g)
if "Reply: " not in code_only(AN["M7 Build"]["parameters"]["jsCode"]):
    problems.append("alert excerpt not live")
if len(after["nodes"]) != len(ORIG["nodes"]) + 2:
    problems.append("node count %d expected %d" % (len(after["nodes"]), len(ORIG["nodes"]) + 2))
if not after.get("active"):
    problems.append("WF-1 IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  WF-1 versionId=%s active=%s nodes=%d" % (after.get("versionId"), after.get("active"),
                                                  len(after["nodes"])))
sys.exit(1 if problems else 0)
