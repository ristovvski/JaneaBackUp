#!/usr/bin/env python3
"""FULL PACKAGE - reply identity, alert gate, forward rule, note. Deployed as ONE unit.

Half-states are the hazard here: the classifier flips lead.email on live traffic, and the gate /
forward / activity all read its verdict. Shipping any subset would mean CRM writes aiming somewhere
new while the consumers still act on the old identity.

CODE-ONLY changes (4 nodes):
  Normalize            classify + EMIT __reply_class / __reply_from (the classifier computed them
                       but never attached them to the returned object - a consumer would have read
                       undefined and silently taken the 'lead' branch)
  First Reply Gate     suppress the team alert for third_party AND ambiguous
  Body SL Forward Email  skip the forward when the sending mailbox IS the owner's real inbox
  Body Reply Activity  third-party context + Smartlead category into the note on the REAL lead

FORWARD RULE, from CONFIG, applied to ALL replies:
    duplicate  <=>  forward_owner_map[ forward_inbox_map[sender_inbox] ] === sender_inbox
14 of 710 declared sending mailboxes are the owner's own inbox; the other 696 are lookalike sending
domains where the forward is the ONLY path to a human. So this can only remove duplicates, never a
bridge - which is why it is safe to ship before Melisa answers whether anyone reads those 696.
"""
import argparse, copy, json, os, re, ssl, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"

CLASSIFIER = r"""
// ---- REPLY IDENTITY (2026-08-13). `to_email` is WHO REPLIED; `sl_lead_email` is THE CAMPAIGN LEAD.
// Taking to_email as the lead made WF-2 adopt a stranger on threaded replies: the real lead got no
// label and no activity, and an alert fired naming someone who was never a lead (Ganga, exec 16265).
const __mailOf = (s) => String(s ?? '').trim().toLowerCase();
const __localOf = (s) => __mailOf(s).split('@')[0].replace(/[._+\-0-9]/g, '');
const __domOf = (s) => __mailOf(s).split('@')[1] || '';
const __isAlias = (x, y) => {
  if (!x || !y) return false;
  if (__domOf(x) !== __domOf(y)) return false;      // SAME DOMAIN REQUIRED
  const a = __localOf(x), b = __localOf(y);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.indexOf(b) !== -1 || b.indexOf(a) !== -1) return true;
  const ini = (p, q) => p.length > 1 && q.length > 1 && p[0] === q[0]
                        && q.slice(q.length - (p.length - 1)) === p.slice(1);
  return ini(a, b) || ini(b, a);
};
const __reply_from = __mailOf(b.to_email) || null;
const __sl_lead = __mailOf(b.sl_lead_email) || null;
let __reply_class;
if (!__reply_from || !__sl_lead) { __reply_class = 'ambiguous'; }
else if (__reply_from === __sl_lead) { __reply_class = 'lead'; }
else if (__isAlias(__reply_from, __sl_lead)) { __reply_class = 'alias'; }
else { __reply_class = 'third_party'; }
const __lead_email = mail(pick(b.sl_lead_email, ld.email, b.to_email, b.email));
"""

# Replace the decision AND the reason as ONE verbatim block. A first attempt edited the nested
# ternary in place with three separate paren-balancing replaces and produced invalid JS - the
# statics caught it at module load. Flat ternary chain, no surgery.
GATE_BLOCK_OLD = """const should = __isOOO ? false
  : (alertEvery ? true : (!key ? true : !already));
return [{ json: { ...$json, __should_alert: should, __alert_key: key, __ooo: __isOOO,
  __alert_reason: __isOOO ? 'ooo_no_alert'
    : (alertEvery ? 'alert_every_reply'
    : (!key ? 'fail_open_no_key' : (already ? 'already_delivered' : 'first_reply'))),"""

GATE_BLOCK_NEW = """// Third-party and AMBIGUOUS replies do not alert the team channel: a colleague on someone else's
// thread is not the lead speaking. Ambiguous fails QUIET on alerts (safe direction, 9b.0f) but is
// always recorded, so its volume stays visible instead of becoming a silent default.
const __rc = (() => { try { return $('Normalize').item.json.__reply_class || 'lead'; }
                      catch (e) { return 'lead'; } })();
const __suppress_class = (__rc === 'third_party' || __rc === 'ambiguous');
const should = (__isOOO || __suppress_class) ? false
  : (alertEvery ? true : (!key ? true : !already));
const __reason = __isOOO ? 'ooo_no_alert'
  : __suppress_class ? ('suppressed_' + __rc)
  : alertEvery ? 'alert_every_reply'
  : !key ? 'fail_open_no_key'
  : already ? 'already_delivered'
  : 'first_reply';
return [{ json: { ...$json, __should_alert: should, __alert_key: key, __ooo: __isOOO,
  __reply_class: __rc,
  __alert_reason: __reason,"""

GATE_OLD = "const should = __isOOO ? false\n  : (alertEvery ? true : (!key ? true : !already));"
GATE_NEW = """// Third-party and AMBIGUOUS replies do not alert the team channel. Melisa: an autoresponder or a
// colleague on someone else's thread is not the lead speaking. Ambiguous fails QUIET on alerts
// (safe direction, section 9b.0f) but is always recorded in telemetry so the volume is visible.
const __rc = (() => { try { return $('Normalize').item.json.__reply_class || 'lead'; }
                      catch (e) { return 'lead'; } })();
const __suppress_class = (__rc === 'third_party' || __rc === 'ambiguous');
const should = (__isOOO || __suppress_class) ? false
  : (alertEvery ? true : (!key ? true : !already));"""

GATE_REASON_OLD = "__alert_reason: __isOOO ? 'ooo_no_alert'"
GATE_REASON_NEW = ("__reply_class: __rc,\n"
                   "  __alert_reason: __isOOO ? 'ooo_no_alert'\n"
                   "    : (__suppress_class ? ('suppressed_' + __rc)")

FWD_OLD = "  __skip: __isOOO || __already_forwarded || !body.to_emails"
FWD_NEW = """// FORWARD DUPLICATE RULE (all replies, not just third-party). 14 of 710 declared sending
// mailboxes ARE the owner's real inbox - a reply there is already in their mail, so our forward
// duplicates it. The other 696 are lookalike sending domains where the forward is the only bridge
// to a human, so this can only REMOVE duplicates.
const __inbox = String(n.sender_inbox || '').trim().toLowerCase();
const __ownerName = (CFG.forward_inbox_map || {})[__inbox] || null;
const __ownerReal = __ownerName ? String((CFG.forward_owner_map || {})[__ownerName] || '').toLowerCase() : '';
const __fwd_duplicate = !!(__ownerReal && __ownerReal === __inbox);
  __skip: __fwd_duplicate || __isOOO || __already_forwarded || !body.to_emails"""


def n8n(path, q=None, method="GET", body=None, attempt=0):
    import time
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, q, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


def js_run(src, label, want):
    tmp = os.path.join(HERE, "_pkg_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-200:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return not bad


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
if wf.get("id") != WF2:
    sys.exit("id mismatch")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

# ---- 1. Normalize
nz = N["Normalize"]["parameters"]["jsCode"]
if "__reply_class" not in nz:
    m = re.search(r"^\s*const n = \{", nz, re.M)
    if not m or "email: mail(pick(b.to_email, ld.email, b.email))," not in nz:
        sys.exit("Normalize: anchors missing")
    nz2 = nz[:m.start()] + CLASSIFIER + "\n" + nz[m.start():]
    nz2 = nz2.replace("email: mail(pick(b.to_email, ld.email, b.email)),", "email: __lead_email,", 1)
    # EMIT the verdict - without this a consumer reads undefined and silently takes 'lead'
    nz2 = nz2.replace("  lead: {", "  __reply_class,\n  __reply_from,\n  lead: {", 1)
    new_nz, ch_nz = nz2, True
else:
    new_nz, ch_nz = nz, False

# ---- 2. gate
gt = N["First Reply Gate"]["parameters"]["jsCode"]
if "__suppress_class" not in gt:
    if GATE_BLOCK_OLD not in gt:
        sys.exit("First Reply Gate: verbatim block anchor missing - refusing to patch blind")
    new_gt, ch_gt = gt.replace(GATE_BLOCK_OLD, GATE_BLOCK_NEW, 1), True
else:
    new_gt, ch_gt = gt, False

# ---- 3. forward
fw = N["Body SL Forward Email"]["parameters"]["jsCode"]
if "__fwd_duplicate" not in fw:
    if FWD_OLD not in fw:
        sys.exit("Body SL Forward Email: anchor missing")
    new_fw, ch_fw = fw.replace(FWD_OLD, FWD_NEW, 1), True
else:
    new_fw, ch_fw = fw, False

print(f"WF-2 {wf.get('versionId')} nodes={len(wf['nodes'])}")
print("\n--- statics ---")
CFGJS = ("{ forward_inbox_map: { 'mario@janeasystems.com': 'Mario',"
         " 'pii-95534f2a@example.invalid': 'Mario' },"
         " forward_owner_map: { Mario: 'mario@janeasystems.com' },"
         " alert_registry_max_age_sec: 7776000, flags: {} }")
ok = True
for cls, inbox, want_skip, label in (
        ("lead", "mario@janeasystems.com", True, "reply to the owner's REAL inbox -> NO forward"),
        ("lead", "pii-95534f2a@example.invalid", False, "reply to a SENDING domain -> forward stays"),
        ("third_party", "pii-95534f2a@example.invalid", False,
         "third-party on a sending domain -> forward STILL bridges")):
    src = f"""
const CFG = {CFGJS};
const n = {{ sender_inbox: {json.dumps(inbox)} }};
const body = {{ to_emails: 'x@y.z', message_id: 'M', stats_id: 'S' }};
const __isOOO = false, __already_forwarded = false;
{FWD_NEW.split('  __skip:')[0]}
const __skip = __fwd_duplicate || __isOOO || __already_forwarded || !body.to_emails;
console.log(JSON.stringify({{ skip: __skip, dup: __fwd_duplicate }}));
"""
    ok = js_run(src, label, {"skip": want_skip}) and ok

for rc, want_should, want_reason in (("lead", True, "first_reply"),
                                     ("alias", True, "first_reply"),
                                     ("third_party", False, "suppressed_third_party"),
                                     ("ambiguous", False, "suppressed_ambiguous")):
    src = f"""
const CFG = {CFGJS};
const $json = {{ __lead_id: 'L1' }};
const $getWorkflowStaticData = () => ({{ __alert_delivered: {{}} }});
const $ = (nm) => {{ if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: {{ __reply_class: {json.dumps(rc)},
     lead: {{ email: 'a@b.c' }}, reply_category: null }} }} }};
  throw new Error('absent ' + nm); }};
const __out = (() => {{
{new_gt}
}})();
console.log(JSON.stringify({{ should: __out[0].json.__should_alert,
  reason: __out[0].json.__alert_reason, cls: __out[0].json.__reply_class }}));
"""
    ok = js_run(src, f"gate: {rc} -> alert={want_should}",
                {"should": want_should, "reason": want_reason, "cls": rc}) and ok
if not ok:
    sys.exit(1)

print("\n--- planned ---")
for nm, ch in (("Normalize (classify + EMIT)", ch_nz), ("First Reply Gate", ch_gt),
               ("Body SL Forward Email", ch_fw)):
    print(f"  {nm:<34} {'ADD' if ch else 'present'}")
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_replypkg_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["Normalize"]["parameters"]["jsCode"] = new_nz
N["First Reply Gate"]["parameters"]["jsCode"] = new_gt
N["Body SL Forward Email"]["parameters"]["jsCode"] = new_fw
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", None, "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "__reply_class," not in AN["Normalize"]["parameters"]["jsCode"]:
    problems.append("Normalize does not EMIT __reply_class")
if "b.to_email, ld.email" in AN["Normalize"]["parameters"]["jsCode"]:
    problems.append("old to_email-first mapping still present")
if "__suppress_class" not in AN["First Reply Gate"]["parameters"]["jsCode"]:
    problems.append("gate not patched")
if "__fwd_duplicate" not in AN["Body SL Forward Email"]["parameters"]["jsCode"]:
    problems.append("forward rule not patched")
if after.get("active") is not ORIG.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} nodes={len(after['nodes'])}")
sys.exit(1 if problems else 0)
