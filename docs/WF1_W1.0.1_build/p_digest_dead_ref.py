#!/usr/bin/env python3
"""ITEM 1 - dnc_morning_digest: `No Match Count` references `$('I04 Status')`, deleted 3 Sep.

Five digests lost; WF-ERR alerted every time.

THE DECISION I OWN. The auditor offered two candidates and preferred (b) "drop the `...prev` spread
and return only the no_match_* fields, letting Compose assemble". **(b) would have silently emptied
the digest** - and it is worth writing down why, because it is this estate's signature failure.

`Compose` reads 37 fields off its input item (`d.__sl`, `d.pd_by_source`, `d.changelog_24h`,
`d.missed`, `d.gate_healthy`, …). `No Match Count` produces exactly THREE of them
(`no_match_24h`, `__nomatch_readable`, `__nomatch_error`). The other 34 exist only because every
code node in this chain spreads its predecessor's object forward - `Changelog Count` spreads
`$('Sched Agg')`, `Sched Agg` spreads `$('Pick Scheduled')`, and so on back to `Window`. Drop the
spread and `Compose` still runs, still posts, and every section reports `n/a`: a green-looking
digest that measures nothing. A write that reports success while achieving nothing.

So: keep the spread, fix the OWNER. The context owner is the code node immediately upstream of the
`Ops Channel History` HTTP call - `Changelog Count`, whose own header comment already says
"Replaces the old `I04 Status`". The 3 Sep simplification swapped the node and missed this
reference. That is B12 verbatim: `$json` does not survive an HTTP node, so context is recovered
from the node that OWNS it, by name - and when that node is replaced, every by-name reader has to
be re-pointed.

WHAT THE LINE NOW REPORTS: unchanged in meaning - `no_match_24h`, the count of "no match found"
warnings in the ops channel over the window. The dead reference was never about the no-match count
itself; it was the carrier of everything the digest had accumulated before it. The CRM change-log
count the README mentions is already reported, by `Changelog Count` -> `d.changelog_24h`, and it
survives to `Compose` only once the spread is reading a node that exists.
"""
import argparse
import re
import copy
import json
import os
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
DG = "qJKfR602wV9yfFrj"

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


wf = n8n("/api/v1/workflows/%s" % DG)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["No Match Count"]["parameters"]["jsCode"]

OLD = "const prev = $('I04 Status').first().json;"
if OLD not in js:
    sys.exit("the dead reference is not present verbatim - re-read before patching")
if "Changelog Count" not in N:
    sys.exit("`Changelog Count` absent: the intended context owner does not exist")

NEW = """// CONTEXT OWNER, not a data source. Every code node in this chain spreads its predecessor's
// accumulated object forward, because the HTTP node between them destroys $json (B12). This read
// used to point at `I04 Status`; the 3 Sep simplification replaced that node with
// `Changelog Count` (see its own header comment) and left this reference dangling, which cost five
// digests. The spread MUST stay: `Compose` consumes 37 fields and this node produces 3 of them, so
// returning only the no_match_* fields would post a digest with every section reading 'n/a'.
const prev = $('Changelog Count').first().json;"""
N["No Match Count"]["parameters"]["jsCode"] = js.replace(OLD, NEW, 1)
PATCHED = N["No Match Count"]["parameters"]["jsCode"]

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True


def run(code, harness, pick):
    src = harness + "\nconst OUT = (() => {\n" + code + "\n})();\nconsole.log(JSON.stringify(" \
          + pick + "));\n"
    tmp = os.path.join(HERE, "_dg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


# the accumulated object as `Changelog Count` really emits it (fields Compose consumes)
PREV = {"__sl": [{"campaign_name": "[Events Visiting] [FinovateFall 2026]", "sends_24h": 12}],
        "__hr_readable": True, "__hr_active": 3, "pd_new_leads": 7,
        "pd_by_source": {"smartlead": 5, "heyreach": 2}, "missed": [], "missed_count": 0,
        "gate_healthy": True, "dnc_active": 25653,
        "__changelog_readable": True, "changelog_24h": 215, "changelog_leads": 130}
CFG = {"no_match_pattern": "no match found"}


def harness(hist):
    return ("const PREV = %s; const CFG = %s; const HIST = %s;\n"
            "const $ = (n) => ({ first: () => ({ json: n === 'Changelog Count' ? PREV\n"
            "                       : n === 'CONFIG' ? CFG : (() => { throw new Error("
            "'unresolved node reference: ' + n) })() }) });\n"
            "const $input = { first: () => ({ json: HIST }) };\n"
            % (json.dumps(PREV), json.dumps(CFG), json.dumps(hist)))


CASES = [
    ("readable, 2 hits",
     {"ok": True, "messages": [{"text": "WARN no match found for x"}, {"text": "hello"},
                               {"text": "No Match Found again"}]},
     lambda o: o["__nomatch_readable"] is True and o["no_match_24h"] == 2
     and o["__history_saturated"] is False),
    ("unreadable history keeps the accumulated context",
     {"ok": False, "error": "not_in_channel"},
     lambda o: o["__nomatch_readable"] is False and o["__nomatch_error"] == "not_in_channel"),
    ("saturated history is flagged",
     {"ok": True, "messages": [{"text": "no match found"}] * 200},
     lambda o: o["__history_saturated"] is True and o["no_match_24h"] == 200),
]

for label, hist, check in CASES:
    got, err = run(PATCHED, harness(hist), "OUT[0].json")
    if err:
        print("  [FAIL] %-46s node error: %s" % (label, err))
        ok = False
        continue
    good = check(got)
    # the whole point: every field Compose reads must survive this node
    survived = all(k in got for k in PREV)
    print("  [%s] %-46s all %d carried fields survive=%s" % (
        "ok " if (good and survived) else "FAIL", label, len(PREV), survived))
    if not (good and survived):
        ok = False
        print("         got keys: %s" % sorted(got)[:14])

# non-vacuity: the OLD code must FAIL the same harness, or the statics prove nothing
got, err = run(js, harness(CASES[0][1]), "OUT[0].json")
dead_fails = err is not None and "unresolved node reference: I04 Status" in err
print("  [%s] %-46s old code errors on the same harness" % ("ok " if dead_fails else "FAIL",
                                                            "non-vacuity"))
ok = ok and dead_fails

def code_only(js):
    """Assertions run on CODE, never on prose. Twice now a post-deploy check has false-alarmed on
    its own explanatory comment - here the comment necessarily names `I04 Status`."""
    out = []
    for line in js.splitlines():
        if line.strip().startswith("//"):
            continue
        out.append(re.sub(r"//.*$", "", line))
    return "\n".join(out)


if "I04 Status" in code_only(PATCHED):
    print("  [FAIL] dead reference still present in the patched CODE")
    ok = False
else:
    print("  [ok ] no `I04 Status` reference remains in the code (comments may still name it)")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "digest_backup_before_dead_ref_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: digest_backup_before_dead_ref_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % DG, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % DG)
AN = {n["name"]: n for n in after["nodes"]}
live = AN["No Match Count"]["parameters"]["jsCode"]
problems = []
live_code = code_only(live)
if "$('Changelog Count')" not in live_code:
    problems.append("new context owner not live")
if "$('I04 Status')" in live_code:
    problems.append("dead reference still live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
if not after.get("active"):
    problems.append("WORKFLOW IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  dnc_morning_digest versionId=%s active=%s nodes=%d" % (
    after.get("versionId"), after.get("active"), len(after["nodes"])))
sys.exit(1 if problems else 0)
