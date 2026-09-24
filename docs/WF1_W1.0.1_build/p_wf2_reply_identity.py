#!/usr/bin/env python3
"""WF-2 reply identity: the lead is `sl_lead_email`, the sender is `to_email`, and they differ.

THE DEFECT, one line (Normalize:103):
    email: mail(pick(b.to_email, ld.email, b.email)),
`to_email` is whoever hit reply. On a threaded reply that is not the campaign lead, so WF-2 adopted
the wrong human: person search missed, no lead resolved, the REAL lead got no label and no activity,
and an alert fired naming a stranger. `sl_lead_email` - the truth - was in the payload and unused.

CLASSIFICATION (Nik's option 3), computed once in Normalize so every downstream consumer agrees:
  lead        to_email == sl_lead_email
  alias       same domain AND local-parts related  -> TREAT AS THE LEAD (Rachel/Joseph/Conrad class)
  third_party otherwise                            -> suppress channel alert (Marie-Anne class)
  ambiguous   either field missing                 -> EXPLICIT branch, never a silent default

`lead.email` is now ALWAYS the campaign lead when known, for every class - so CRM writes land on the
real record even when the alert is suppressed. `__reply_from` carries who actually wrote.

The alias test is deliberately conservative: same domain is REQUIRED, so a stranger at another
company can never be absorbed into a lead's identity. Within a domain it accepts containment or
initial+surname, which is what the three real cases are (jfarrar/joseph.farrar, ravery/rachel.avery,
kevin.conrad.morales/conrad.morales) and what Marie-Anne is not (marieanneganga vs andreatassistro:
same domain, unrelated name).
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
FIXTURE_EXECS = ["12612", "12622", "12637", "16265"]

OLD = "email: mail(pick(b.to_email, ld.email, b.email)),"
NEW = "email: __lead_email,"

CLASSIFIER = r"""
// ---- REPLY IDENTITY (2026-08-13). `to_email` is WHO REPLIED; `sl_lead_email` is THE CAMPAIGN LEAD.
// Taking to_email as the lead identity made WF-2 adopt a stranger on threaded replies: the real
// lead got no label and no activity, and an alert fired naming someone who was never a lead.
// Classified once, here, so the gate / CRM writes / forward / telemetry cannot disagree.
const __mailOf = (s) => String(s ?? '').trim().toLowerCase();
const __localOf = (s) => __mailOf(s).split('@')[0].replace(/[._+\-0-9]/g, '');
const __domOf = (s) => __mailOf(s).split('@')[1] || '';
const __isAlias = (x, y) => {
  if (!x || !y) return false;
  if (__domOf(x) !== __domOf(y)) return false;      // SAME DOMAIN REQUIRED - conservative on purpose
  const a = __localOf(x), b = __localOf(y);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.indexOf(b) !== -1 || b.indexOf(a) !== -1) return true;   // conrad.morales in kevin.conrad.morales
  const ini = (p, q) => p.length > 1 && q.length > 1 && p[0] === q[0]
                        && q.slice(q.length - (p.length - 1)) === p.slice(1);
  return ini(a, b) || ini(b, a);                     // jfarrar vs josephfarrar
};
const __reply_from = __mailOf(b.to_email) || null;
const __sl_lead = __mailOf(b.sl_lead_email) || null;
let __reply_class;
if (!__reply_from || !__sl_lead) {
  // AMBIGUOUS is an explicit branch, never a silent default - a missing field must not decide
  // policy by accident. Downstream suppresses the alert (fail-quiet is safe) but still records.
  __reply_class = 'ambiguous';
} else if (__reply_from === __sl_lead) {
  __reply_class = 'lead';
} else if (__isAlias(__reply_from, __sl_lead)) {
  __reply_class = 'alias';
} else {
  __reply_class = 'third_party';
}
// the LEAD's address wins for every class, so CRM writes land on the real record even when the
// alert is suppressed. Only if Smartlead gave us no lead address do we fall back to the sender.
const __lead_email = mail(pick(b.sl_lead_email, ld.email, b.to_email, b.email));
"""


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


print("pulling the four REAL payloads as fixtures")
fixtures = {}
for ex in FIXTURE_EXECS:
    det = n8n(f"/api/v1/executions/{ex}", {"includeData": "true"})
    rd = (((det or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        wh = rd["Webhook"][0]["data"]["main"][0][0]["json"]
        body = wh.get("body") if isinstance(wh.get("body"), dict) else wh
        fixtures[ex] = body
        print(f"   exec {ex}: to={body.get('to_email')!r} lead={body.get('sl_lead_email')!r}")
    except Exception as e:
        print(f"   exec {ex}: UNREADABLE ({e}) - refusing to test on a synthetic substitute")
if len(fixtures) != len(FIXTURE_EXECS):
    sys.exit("not all fixtures available")

wf = n8n(f"/api/v1/workflows/{WF2}")
if wf.get("id") != WF2:
    sys.exit("id mismatch")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
nz = N["Normalize"]["parameters"]["jsCode"]
need = "__reply_class" not in nz
if need and OLD not in nz:
    sys.exit(f"Normalize: anchor missing, refusing to patch blind:\n  {OLD}")
if need:
    # The classifier must be defined BEFORE the object literal that consumes __lead_email.
    # WF-2's Normalize builds `const n = { ... }` across ~70 lines and returns it at the very end
    # (`return [{ json: n }];`), so inserting before the return would place the definition AFTER its
    # use. Anchor on the start of that object instead, and fail loudly rather than guess.
    import re as _re
    m = _re.search(r"^\s*const n = \{", nz, _re.M)
    if not m:
        sys.exit("Normalize: could not find `const n = {` - refusing to place the classifier blind")
    i = m.start()
    new_nz = nz[:i] + CLASSIFIER + "\n" + nz[i:].replace(OLD, NEW, 1)
else:
    new_nz = nz

HARNESS = """
const b = __BODY__;
const ld = (b.lead || {});
const mail = (s) => (s == null ? null : String(s).trim().toLowerCase());
const pick = (...v) => { for (const x of v) if (x !== undefined && x !== null && x !== '') return x; return null; };
__CLASSIFIER__
console.log(JSON.stringify({ cls: __reply_class, lead_email: __lead_email,
                             reply_from: __reply_from }));
"""


def run(ex, want):
    src = (HARNESS.replace("__BODY__", json.dumps(fixtures[ex]))
                  .replace("__CLASSIFIER__", CLASSIFIER))
    tmp = os.path.join(HERE, "_ident_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] exec {ex}: {(p.stderr or '').strip()[-200:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] exec {ex}  cls={got['cls']!r} "
          f"lead={got['lead_email']} from={got['reply_from']}")
    for x in bad:
        print(f"           {x}")
    return not bad


print("\n--- statics on the FOUR REAL payloads ---")
ok = True
ok = run("12622", {"cls": "alias", "lead_email": "pii-1011b46b@example.invalid",
                   "reply_from": "pii-e56d5459@example.invalid"}) and ok
ok = run("12637", {"cls": "alias", "lead_email": "pii-399e6070@example.invalid",
                   "reply_from": "pii-3d090878@example.invalid"}) and ok
ok = run("12612", {"cls": "alias", "lead_email": "pii-6e4e8b43@example.invalid",
                   "reply_from": "pii-9efda044@example.invalid"}) and ok
ok = run("16265", {"cls": "third_party", "lead_email": "pii-eb7de9be@example.invalid",
                   "reply_from": "pii-10d2dcec@example.invalid"}) and ok

print("\n--- synthetic edge cases (the ones the real four cannot cover) ---")
EDGE = [("same address", {"to_email": "pii-22fdb3ff@example.invalid", "sl_lead_email": "pii-22fdb3ff@example.invalid"},
         {"cls": "lead", "lead_email": "pii-22fdb3ff@example.invalid"}),
        ("different DOMAIN, similar name -> NOT alias",
         {"to_email": "pii-c749ea28@example.invalid", "sl_lead_email": "pii-1011b46b@example.invalid"},
         {"cls": "third_party", "lead_email": "pii-1011b46b@example.invalid"}),
        ("missing sl_lead_email -> ambiguous, falls back to sender",
         {"to_email": "pii-22fdb3ff@example.invalid"}, {"cls": "ambiguous", "lead_email": "pii-22fdb3ff@example.invalid"}),
        ("missing to_email -> ambiguous, lead still the lead",
         {"sl_lead_email": "pii-22fdb3ff@example.invalid"}, {"cls": "ambiguous", "lead_email": "pii-22fdb3ff@example.invalid"}),
        ("case/whitespace differences are not a third party",
         {"to_email": " pii-22fdb3ff@example.invalid ", "sl_lead_email": "pii-22fdb3ff@example.invalid"}, {"cls": "lead"})]
for label, body, want in EDGE:
    fixtures["__edge"] = body
    ok = run("__edge", want) and ok
    print(f"        ^ {label}")
if not ok:
    sys.exit(1)

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()
print("\n--- planned ---")
print(f"  Normalize: classify reply identity, lead.email := sl_lead_email  "
      f"({'ADD' if need else 'present'})")
print("  emits: __reply_class, __reply_from  (consumers land in the NEXT step)")
if not a.deploy or not need:
    print("\n--deploy not given (or already applied): nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_identity_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["Normalize"]["parameters"]["jsCode"] = new_nz
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", None, "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
js = AN["Normalize"]["parameters"]["jsCode"]
problems = []
if "__reply_class" not in js:
    problems.append("classifier missing")
if OLD in js:
    problems.append("the to_email-first mapping is STILL present")
if after.get("active") is not ORIG.get("active"):
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} nodes={len(after['nodes'])}")
