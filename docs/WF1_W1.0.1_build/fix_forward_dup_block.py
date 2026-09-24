#!/usr/bin/env python3
"""HOTFIX - Body SL Forward Email: `Unexpected identifier __inbox`. Forward path down for ALL replies.

MY BUG, shipped last night. The forward duplicate-rule patch anchored on

    __skip: __isOOO || __already_forwarded || !body.to_emails

which sits INSIDE the `return [{ json: { ... } }]` object literal. Prepending `const __inbox = ...`
declarations there put STATEMENTS between object properties - a syntax error. The node has thrown on
every reply since.

Exactly the class my own rule from yesterday names: do not surgically edit inside a structure you
have not re-read. The helper must be declared BEFORE the return, and only the boolean may appear in
the `__skip` expression - the same shape as the OOO helper fix.

Good news, and it is the system working: WF-2R replayed the crashed event within the minute
(P0-1b left the key unclaimed, so it stayed replayable). Nothing was lost. But the forward is the
delivery mechanism for 696 of 710 mailboxes (section 9e), so this is a live outage of reply delivery.
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

HELPER = """
// FORWARD DUPLICATE RULE (section 9e). 14 of 710 declared sending mailboxes ARE an owner's real
// inbox - a reply there is already in their mail. The other 696 are lookalike sending domains that
// nobody reads, where the forward is the ONLY path to a human. So this can only remove duplicates.
// Declared HERE, before the return: the previous version put these statements inside the object
// literal and the node threw `Unexpected identifier __inbox` on every reply.
const __inbox = String(n.sender_inbox || '').trim().toLowerCase();
const __ownerName = (CFG.forward_inbox_map || {})[__inbox] || null;
const __ownerReal = __ownerName
  ? String((CFG.forward_owner_map || {})[__ownerName] || '').toLowerCase() : '';
const __fwd_duplicate = !!(__ownerReal && __ownerReal === __inbox);
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


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["Body SL Forward Email"]["parameters"]["jsCode"]

# 1. strip the badly-placed block wherever it landed
lines = js.splitlines()
bad = [i for i, l in enumerate(lines)
       if l.strip().startswith(("const __inbox", "const __ownerName", "const __ownerReal",
                                "const __fwd_duplicate"))
       or l.strip().startswith("// FORWARD DUPLICATE RULE")
       or l.strip().startswith("// mailboxes ARE the owner")
       or l.strip().startswith("// to a human, so this can only REMOVE")
       or l.strip().startswith("// inbox - a reply there is already")]
print(f"lines carrying the mis-placed block: {len(bad)}  -> {bad}")
cleaned = "\n".join(l for i, l in enumerate(lines) if i not in bad)
# also drop any comment fragments left from the first version
cleaned = re.sub(r"^// (mailboxes ARE|to a human|inbox - a reply).*\n", "", cleaned, flags=re.M)

# 2. put the boolean back into __skip (idempotent), helper declared before the return
if "__fwd_duplicate ||" not in cleaned:
    m = re.search(r"^(\s*)__skip: ", cleaned, re.M)
    if not m:
        sys.exit("no __skip line found")
    cleaned = re.sub(r"^(\s*)__skip: ", r"\1__skip: __fwd_duplicate || ", cleaned, count=1,
                     flags=re.M)
anchor = "const __fkey = (() => {"
if anchor not in cleaned:
    sys.exit("helper anchor (const __fkey) missing - refusing to place the block blind")
new_js = cleaned.replace(anchor, HELPER + "\n" + anchor, 1)

print("\n--- statics: EXECUTE the repaired body (a syntax check would have passed the bug) ---")
CFGJS = ("{ forward_inbox_map: { 'mario@janeasystems.com': 'Mario',"
         " 'pii-95534f2a@example.invalid': 'Mario' },"
         " forward_owner_map: { Mario: 'mario@janeasystems.com' }, fields: {} }")
ok = True
for inbox, want_skip, label in (
        ("mario@janeasystems.com", True, "owner's REAL inbox -> skip (duplicate)"),
        ("pii-95534f2a@example.invalid", False, "sending domain -> forward (the bridge)"),
        ("", False, "unknown inbox -> forward (never silently drop delivery)")):
    src = f"""
const CFG = {CFGJS};
const NORM = {{ sender_inbox: {json.dumps(inbox)}, reply_category: null,
                reply: {{}}, lead: {{ email: 'a@b.c' }} }};
const $json = {{ __forward_to: 'rune@janeasystems.com', __message_id: 'M', __stats_id: 'S',
                 __history: [] }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Dedupe') return {{ item: {{ json: {{ __dedupe_key: 'K' }} }} }};
  throw new Error('absent ' + nm);
}};
const $getWorkflowStaticData = () => ({{ wf2_seen: {{}} }});
const __out = (() => {{
{new_js}
}})();
console.log(JSON.stringify({{ skip: __out[0].json.__skip,
                              dup: __out[0].json.__forward_ooo === undefined ? null : null }}));
"""
    tmp = os.path.join(HERE, "_fwdfix.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-260:]}")
        ok = False
        continue
    got = json.loads(p.stdout.strip())
    good = got.get("skip") is want_skip
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  skip={got.get('skip')}")
    ok = good and ok
if not ok:
    sys.exit(1)

print("\n--- planned ---")
print("  Body SL Forward Email: helper moved OUT of the object literal, __skip keeps the boolean")
if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)
stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_fwdfix_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["Body SL Forward Email"]["parameters"]["jsCode"] = new_js
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", None, "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
fj = AN["Body SL Forward Email"]["parameters"]["jsCode"]
problems = []
if "__fwd_duplicate ||" not in fj:
    problems.append("skip rule missing")
if fj.index("const __inbox") > fj.index("__skip:"):
    problems.append("helper is STILL after the skip line")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')}")
