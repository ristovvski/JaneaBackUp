#!/usr/bin/env python3
"""ITEM 2 - port `__auth_warn_at` from staticData to the atomic claims row `wf2_auth_notice`.

THE BUG. `Verify Secret` rate-limits its own warning with `sd.__auth_warn_at` /
`sd.__auth_suppressed`. staticData is persisted as ONE object at execution end, so overlapping
executions each read the same stale timestamp and each decide to warn: the 09-04 burst of 135 WF-2
executions produced 135 posts. Fourth and last of the WF-2 stores in this class - the other three
were ported 3 Sep.

THE PORT, as briefed:
  row `wf2_auth_notice` in `euyostwJYfJefItC`, state in `evidence` as
  {mode, last_posted_date, suppressed_since_last}
  post iff  mode != stored.mode  OR  today != stored.last_posted_date
  severity split: unconfigured (traffic ACCEPTED) -> on change + once/day
                  missing / mismatch (a DROP)     -> every time
  row missing or table unreadable -> post (alert gates fail OPEN, 9b.0f)
  one closing post when the mode leaves a noisy state, so the channel shows resolution
  suppressed_since_last is carried into the post - it is the actionable number

FOUR NODES, teed off the existing warn branch:

  Verify Secret ─▶ IF Authentic                          (processing path, untouched)
                └▶ DT Auth Notice Get ─▶ Auth Notice Decide ─▶ DT Auth Notice Claim
                                                              ─▶ Auth Notice Ctx ─▶ IF Auth Warn
                                                                                  ─▶ Ops Warn …

CLAIM BEFORE POST - and this DIVERGES from the alert registry's claim-after-delivery on purpose.
For a lead alert, claiming first risks silencing an alert that never reached anyone: a lost lead.
For flood control the failure modes are reversed - claim-after means a failed write re-posts on
every subsequent event, which is exactly the flood being fixed, while claim-first at worst drops one
infra notice that tomorrow's heartbeat re-raises. Different data, different direction.

RESIDUAL, stated: the row is atomic but the read-then-write is not a compare-and-swap (n8n's
dataTable has no conditional update). Two executions in the same instant can both see
"not posted today" and both post. That turns 135 posts into at most a rare 2 - it does not turn it
into 1, and pretending otherwise would be the third time this estate mistook a narrowed window for
a closed one.

`Verify Secret` keeps its two staticData writes as a WRITE-ONLY rollback copy, matching what the
3 Sep ports left in place. Nothing reads them.
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
WF2 = "jp7rum9Z0YDJkQWv"
TABLE = "euyostwJYfJefItC"
ROWKEY = "wf2_auth_notice"

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
    out = []
    for line in js.splitlines():
        if line.strip().startswith("//"):
            continue
        out.append(re.sub(r"//.*$", "", line))
    return "\n".join(out)


wf = n8n("/api/v1/workflows/%s" % WF2)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.setdefault("connections", {})
if "Auth Notice Decide" in N:
    sys.exit("auth-notice port already present")
for req in ("Verify Secret", "IF Auth Warn", "Ops Warn Bad Secret", "IF Authentic", "CONFIG"):
    if req not in N:
        sys.exit("missing expected node: %s" % req)

# ---------------------------------------------------------------- A: Verify Secret loses the decision
vs = N["Verify Secret"]["parameters"]["jsCode"]
OLD_BLOCK_START = "const sd = $getWorkflowStaticData('global');"
if OLD_BLOCK_START not in vs:
    sys.exit("Verify Secret staticData block not found verbatim")
start = vs.index(OLD_BLOCK_START)
end = vs.index("const hint = [")
if end < start:
    sys.exit("Verify Secret shape unexpected - hint block precedes the staticData block")

NEW_BLOCK = """// W2.STATE (2026-09-08) - the notice rate-limit MOVED to the claims table, row `wf2_auth_notice`.
// staticData is persisted as ONE object at execution end, so the 09-04 burst of 135 executions each
// read the same stale __auth_warn_at and each warned. This node no longer decides anything about
// posting - `Auth Notice Decide` does, from the atomic row. The two writes below are kept
// WRITE-ONLY as the documented rollback copy, exactly as the 3 Sep ports left theirs. Nothing
// reads them; deleting them is the second half of this port, once a live burst has proven the row.
const sd = $getWorkflowStaticData('global');
sd.__auth_warn_at = Number(sd.__auth_warn_at ?? 0);
if (mode !== 'valid') sd.__auth_suppressed = Number(sd.__auth_suppressed ?? 0) + 1;
"""
vs_new = vs[:start] + NEW_BLOCK + vs[end:]
# the emitted item loses __auth_warn / __auth_suppressed: Decide owns both now
vs_new = vs_new.replace(
    "return [{ json: { __auth_ok: ok, __auth_mode: mode, __auth_warn: warn,\n"
    "                  __auth_suppressed: suppressed, __auth_hint: hint,",
    "return [{ json: { __auth_ok: ok, __auth_mode: mode, __auth_hint: hint,", 1)
if "__auth_warn:" in code_only(vs_new):
    sys.exit("Verify Secret still emits __auth_warn - the return shape did not match verbatim")
N["Verify Secret"]["parameters"]["jsCode"] = vs_new

# ---------------------------------------------------------------- B: the decision node
DECIDE = r"""
// Auth-notice suppression, from the ATOMIC row instead of staticData.
const CFG = $('CONFIG').item.json;
const v = $('Verify Secret').item.json;
const mode = String(v.__auth_mode || 'unknown');
const row = $json;

// POSITIVE success shape. n8n's dataTable error shape is NOT uniform: some operations return
// {error:...}, others echo the ORIGINAL input items with no marker at all. A filter that tests
// negatively for `.error` therefore treats an echoed input as a successful read of a row that does
// not exist - which is why this checks for the real row and treats anything else as broken.
const isRow = !!(row && row.claim_key === 'wf2_auth_notice' && row.family === 'wf2_auth_notice');
const lookupBroken = !!(row && (row.error || row.__error))
                  || (!!row && Object.keys(row).length > 0 && !isRow);

let st = {};
if (isRow) { try { st = JSON.parse(row.evidence || '{}'); } catch (e) { st = {}; } }
const storedMode = isRow ? (st.mode == null ? null : String(st.mode)) : null;
const storedDate = isRow ? String(st.last_posted_date ?? String(row.claimed_at || '').slice(0, 10))
                         : null;
const suppressed = isRow ? Number(st.suppressed_since_last ?? 0) : 0;
const today = new Date().toISOString().slice(0, 10);
const dropping = (mode === 'missing' || mode === 'mismatch');

let post, why;
if (mode === 'valid') {
  // exactly ONE closing post, and only if the stored state says we had been noisy. A valid event
  // with no row at all is a quiet endpoint, not a resolution - it must not announce itself.
  post = !!(isRow && storedMode && storedMode !== 'valid');
  why = post ? ('resolved:' + storedMode + '->valid') : 'armed_and_quiet';
} else if (lookupBroken) {
  post = true; why = 'dt_unavailable_fail_open';       // alert gates fail OPEN (9b.0f)
} else if (!isRow) {
  post = true; why = 'no_row_first_notice';
} else if (dropping) {
  post = true; why = 'drop_every_time';                // someone posting without the secret is not noise
} else if (mode !== storedMode) {
  post = true; why = 'mode_change:' + storedMode + '->' + mode;
} else if (today !== storedDate) {
  post = true; why = 'daily_heartbeat';
} else {
  post = false; why = 'already_posted_today';
}

// suppressed_since_last only counts events we DECLINED to announce, so a quiet armed endpoint
// never inflates it.
const nextSuppressed = post ? 0 : (mode === 'valid' ? suppressed : suppressed + 1);
const next = { mode, suppressed_since_last: nextSuppressed,
               last_posted_date: post ? today : (storedDate ?? null) };

return [{ json: { ...v, __auth_warn: post, __auth_warn_why: why,
                  __auth_suppressed: post ? suppressed : 0,
                  __notice_key: 'wf2_auth_notice',
                  __notice_row: JSON.stringify(next),
                  __notice_lookup_broken: lookupBroken } }];
"""

CTX = r"""
// B12: $json here is the UPSERT RESPONSE - every __auth_* field is gone. Recover the decision from
// the node that owns it, by name, exactly as the rest of the estate does after a write.
const d = $('Auth Notice Decide').item.json;
const r = $json || {};
// Informational ONLY. The upsert result shape is not documented and this must never gate the post:
// a wrong guess here would silence a real notice, which is the failure this whole item is fixing.
const wrote = !!(r.claim_key === 'wf2_auth_notice' || r.id || r.success === true);
return [{ json: { ...d, __notice_written: wrote } }];
"""

def dt(name, pos, params, on_err="continueRegularOutput", always=None, retry=None):
    n = {"parameters": params, "id": None, "name": name, "type": "n8n-nodes-base.dataTable",
         "typeVersion": 1, "position": pos, "onError": on_err}
    if always is not None:
        n["alwaysOutputData"] = always
    if retry is not None:
        n["retryOnFail"] = retry
    n.pop("id")
    return n


def code(name, pos, js):
    return {"parameters": {"jsCode": js, "mode": "runOnceForAllItems"}, "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}


NEW_NODES = [
    dt("DT Auth Notice Get", [660, 200],
       {"resource": "row", "operation": "get",
        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                    "keyValue": ROWKEY}]},
        "options": {}},
       # a read whose EMPTY result is the normal case emits nothing and skips the whole chain -
       # the first notice ever would be silently lost without this
       always=True),
    code("Auth Notice Decide", [820, 200], DECIDE),
    dt("DT Auth Notice Claim", [980, 200],
       {"resource": "row", "operation": "upsert",
        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                    "keyValue": ROWKEY}]},
        "columns": {"mappingMode": "defineBelow", "value": {
            "claim_key": ROWKEY,
            "family": ROWKEY,
            "workflow": "WF-2",
            "event_time": "={{ new Date().toISOString() }}",
            "claimed_at": "={{ new Date().toISOString() }}",
            "evidence": "={{ $('Auth Notice Decide').item.json.__notice_row }}"}},
        "options": {}},
       retry=True),
    code("Auth Notice Ctx", [1140, 200], CTX),
]
wf["nodes"] += NEW_NODES
N["IF Auth Warn"]["position"] = [1300, 200]
N["Ops Warn Bad Secret"]["position"] = [1500, 200]

# ---------------------------------------------------------------- C: rewire
vs_conn = (C.get("Verify Secret") or {}).get("main") or [[]]
kept = [l for l in (vs_conn[0] or []) if l and l.get("node") != "IF Auth Warn"]
if len(kept) == len(vs_conn[0] or []):
    sys.exit("Verify Secret -> IF Auth Warn link not found; refusing to rewire blind")
kept.append({"node": "DT Auth Notice Get", "type": "main", "index": 0})
C["Verify Secret"] = {"main": [kept]}
C["DT Auth Notice Get"] = {"main": [[{"node": "Auth Notice Decide", "type": "main", "index": 0}]]}
C["Auth Notice Decide"] = {"main": [[{"node": "DT Auth Notice Claim", "type": "main", "index": 0}]]}
C["DT Auth Notice Claim"] = {"main": [[{"node": "Auth Notice Ctx", "type": "main", "index": 0}]]}
C["Auth Notice Ctx"] = {"main": [[{"node": "IF Auth Warn", "type": "main", "index": 0}]]}

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True


def run(js, harness, pick="OUT[0].json"):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(" \
          + pick + "));\n"
    tmp = os.path.join(HERE, "_an.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
YEST = "2026-09-07"


def row(mode, date, sup):
    return {"claim_key": ROWKEY, "family": ROWKEY, "workflow": "WF-2",
            "claimed_at": date + "T06:00:00.000Z",
            "evidence": json.dumps({"mode": mode, "last_posted_date": date,
                                    "suppressed_since_last": sup})}


def harness(mode, rowobj):
    v = {"__auth_ok": mode in ("valid", "unconfigured"), "__auth_mode": mode,
         "__auth_hint": "1.2.3.4 / curl", "__auth_event": "EMAIL_REPLY", "__auth_campaign": "c1"}
    return ("const V = %s; const ROW = %s; const CFG = {};\n"
            "const $ = (n) => ({ item: { json: n === 'Verify Secret' ? V\n"
            "   : n === 'CONFIG' ? CFG : (() => { throw new Error('unresolved node: ' + n) })() } });\n"
            "const $json = ROW;\n" % (json.dumps(v), json.dumps(rowobj)))


CASES = [
    ("missing secret, no row yet", "missing", {},
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "no_row_first_notice"),
    ("unconfigured, already posted today", "unconfigured", row("unconfigured", TODAY, 3),
     lambda o: o["__auth_warn"] is False
     and json.loads(o["__notice_row"])["suppressed_since_last"] == 4),
    ("unconfigured, last posted yesterday -> heartbeat", "unconfigured",
     row("unconfigured", YEST, 41),
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "daily_heartbeat"
     and o["__auth_suppressed"] == 41
     and json.loads(o["__notice_row"])["suppressed_since_last"] == 0),
    ("mismatch posts even when already posted today", "mismatch", row("mismatch", TODAY, 0),
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "drop_every_time"),
    # a DROP is governed by "every time", which outranks the mode-change label - same outcome,
    # more informative reason (it says why it will keep posting)
    ("unconfigured -> missing is a drop, not a mode-change note", "missing",
     row("unconfigured", TODAY, 9),
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "drop_every_time"),
    # the mode-change branch that is NOT a drop and NOT the heartbeat: someone cleared the hash
    ("armed -> unconfigured posts on the change alone", "unconfigured", row("valid", TODAY, 0),
     lambda o: o["__auth_warn"] is True
     and o["__auth_warn_why"] == "mode_change:valid->unconfigured"),
    ("secret armed: exactly one closing post", "valid", row("unconfigured", TODAY, 12),
     lambda o: o["__auth_warn"] is True
     and o["__auth_warn_why"] == "resolved:unconfigured->valid"),
    ("armed and stable: silent", "valid", row("valid", TODAY, 0),
     lambda o: o["__auth_warn"] is False and o["__auth_warn_why"] == "armed_and_quiet"),
    ("valid with NO row never announces itself", "valid", {},
     lambda o: o["__auth_warn"] is False and o["__auth_warn_why"] == "armed_and_quiet"),
    ("dataTable error shape -> fail OPEN", "unconfigured", {"error": "table unavailable"},
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "dt_unavailable_fail_open"),
    ("dataTable ECHOED-INPUT error shape -> fail OPEN", "unconfigured",
     {"__auth_mode": "unconfigured", "__auth_ok": True},
     lambda o: o["__auth_warn"] is True and o["__auth_warn_why"] == "dt_unavailable_fail_open"),
    ("quiet armed endpoint never inflates the suppressed count", "valid", row("valid", TODAY, 0),
     lambda o: json.loads(o["__notice_row"])["suppressed_since_last"] == 0),
]

for label, mode, rowobj, check in CASES:
    got, err = run(DECIDE, harness(mode, rowobj))
    if err:
        print("  [FAIL] %-52s node error: %s" % (label, err))
        ok = False
        continue
    good = check(got)
    carried = all(k in got for k in ("__auth_mode", "__auth_hint", "__auth_event",
                                     "__auth_campaign"))
    print("  [%s] %-52s warn=%-5s why=%s" % ("ok " if (good and carried) else "FAIL", label,
                                             got["__auth_warn"], got["__auth_warn_why"]))
    if not (good and carried):
        ok = False
        print("         %s" % json.dumps(got)[:220])

# --- Ctx recovers past the write
CTX_H = ("const D = %s;\n"
         "const $ = (n) => ({ item: { json: n === 'Auth Notice Decide' ? D"
         " : (() => { throw new Error('unresolved node: ' + n) })() } });\n"
         "const $json = {\"claim_key\":\"wf2_auth_notice\",\"family\":\"wf2_auth_notice\"};\n"
         % json.dumps({"__auth_warn": True, "__auth_mode": "missing", "__auth_hint": "h",
                       "__auth_event": "e", "__auth_campaign": "c", "__auth_suppressed": 7}))
got, err = run(CTX, CTX_H)
good = bool(got) and got.get("__auth_warn") is True and got.get("__auth_suppressed") == 7 \
    and got.get("__notice_written") is True
print("  [%s] %-52s %s" % ("ok " if good else "FAIL",
                           "Ctx recovers the decision past the upsert (B12)",
                           "all __auth_* carried" if good else json.dumps(got)[:200]))
ok = ok and good

# --- NON-VACUITY: the old staticData rate-limit floods under concurrency, the row does not.
# n8n hands each overlapping execution its own copy of staticData and persists the LAST writer,
# so every execution in a burst reads the same starting value. That is the 135-post morning.
OLD_RL = """
let warn = false, suppressed = 0;
const every = 3600 * 1000;
if (mode !== 'valid') {
  const last = Number(sd.__auth_warn_at ?? 0);
  sd.__auth_suppressed = Number(sd.__auth_suppressed ?? 0) + 1;
  if (now - last >= every) { warn = true; suppressed = Number(sd.__auth_suppressed) - 1;
    sd.__auth_warn_at = now; sd.__auth_suppressed = 0; }
}
return [{ warn }];
"""
BURST = ("const mode = 'unconfigured'; const now = 1788870000000;\n"
         "// three OVERLAPPING executions, each with its own copy of the same persisted object\n"
         "const results = [0,1,2].map(() => { const sd = { __auth_warn_at: 0,"
         " __auth_suppressed: 0 };\n"
         "  return (() => {" + OLD_RL + "})()[0].warn; });\n")
got, err = run("return results;", BURST, "OUT")
old_floods = got == [True, True, True]
print("  [%s] %-52s old staticData path warns %s" % (
    "ok " if old_floods else "FAIL", "non-vacuity: burst of 3 overlapping executions",
    "3/3 times (the flood)" if old_floods else str(got)))
ok = ok and old_floods

# the same burst against the ROW: first posts, and once the row is written the rest are suppressed
got1, _ = run(DECIDE, harness("unconfigured", {}))
got2, _ = run(DECIDE, harness("unconfigured", row("unconfigured", TODAY, 0)))
row_holds = got1["__auth_warn"] is True and got2["__auth_warn"] is False
print("  [%s] %-52s post then suppress" % ("ok " if row_holds else "FAIL",
                                           "same burst against the atomic row"))
ok = ok and row_holds

if "getWorkflowStaticData" not in code_only(N["Verify Secret"]["parameters"]["jsCode"]):
    print("  [FAIL] the rollback copy was removed - it is meant to stay until a live burst proves the row")
    ok = False
else:
    print("  [ok ] staticData kept WRITE-ONLY as the rollback copy")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass  (%d cases + Ctx + 2 non-vacuity + 1 rollback)" % len(CASES))
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "wf2_backup_before_auth_notice_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: wf2_backup_before_auth_notice_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % WF2, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % WF2)
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in ("DT Auth Notice Get", "Auth Notice Decide", "DT Auth Notice Claim", "Auth Notice Ctx"):
    if nm not in AN:
        problems.append("%s missing" % nm)
if "__auth_warn:" in code_only(AN["Verify Secret"]["parameters"]["jsCode"]):
    problems.append("Verify Secret still decides the warn")
chain = [l["node"] for b in ((AC.get("Auth Notice Ctx") or {}).get("main") or []) for l in b]
if chain != ["IF Auth Warn"]:
    problems.append("Ctx -> IF Auth Warn not wired (got %s)" % chain)
vsk = [l["node"] for b in ((AC.get("Verify Secret") or {}).get("main") or []) for l in b]
if "IF Auth Warn" in vsk:
    problems.append("Verify Secret still feeds IF Auth Warn directly")
if "DT Auth Notice Get" not in vsk:
    problems.append("Verify Secret does not feed the notice branch")
if len(after["nodes"]) != len(ORIG["nodes"]) + 4:
    problems.append("node count %d, expected %d" % (len(after["nodes"]), len(ORIG["nodes"]) + 4))
if not after.get("active"):
    problems.append("WF-2 IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  WF-2 versionId=%s active=%s nodes=%d" % (after.get("versionId"), after.get("active"),
                                                  len(after["nodes"])))
print("  Verify Secret -> %s" % vsk)
sys.exit(1 if problems else 0)
