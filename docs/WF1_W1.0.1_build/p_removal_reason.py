#!/usr/bin/env python3
"""FINDING + FIX: the registry removal path cannot record WHY a row was removed.

`dnc_s4_retirement_removal` (DYb9jArdS7xKs3nA, ACTIVE) is the driver behind the 7,450-row
tombstoning, and its `Build Items` node hardcodes:

    removed_reason: 'rule_change_2026-08-26_melisa'

It reads `row_ids` and `dry_run` from the caller and ignores everything else. So tombstoning Heath
Tarbert's false row through it would file the correction as a **rule change from 26 August that has
nothing to do with him** - a false audit trail, which is worse than none, and precisely the kind of
"the write succeeded, the record is wrong" outcome this estate keeps paying for.

FIX: honour a caller-supplied `removed_reason`, defaulting to the existing constant so every
current caller is byte-identical. Backward compatible by construction, and the statics prove it.
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
RET = "DYb9jArdS7xKs3nA"

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
        if e.code in (429, 500, 502, 503, 504) and att < 5:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:300]))
    except Exception:
        if att < 3:
            time.sleep(6)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n("/api/v1/workflows/%s" % RET)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["Build Items"]["parameters"]["jsCode"]
print("=== Build Items, as live ===")
print(js)

OLD = "removed_reason: 'rule_change_2026-08-26_melisa'"
if OLD not in js:
    sys.exit("hardcoded reason not found verbatim - re-read before patching")
NEW = """removed_reason: (typeof body.removed_reason === 'string' && body.removed_reason.trim())
      ? body.removed_reason.trim().slice(0, 120)
      // Default is the original constant, so every existing caller is byte-identical. It was
      // hardcoded, which meant a correction could only be filed under someone else's rule change.
      : 'rule_change_2026-08-26_melisa'"""
patched = js.replace(OLD, NEW, 1)
N["Build Items"]["parameters"]["jsCode"] = patched

print("\n--- statics ---")
ok = True


def run(code, body, ids=(1, 2)):
    # the node reads $('Webhook').first().json.body - not $json. Getting the harness wrong made all
    # eight cases fail identically, which is what an unmocked accessor looks like.
    src = ("const BODY = %s;\n"
           "const $ = (nm) => ({ first: () => ({ json: { body: BODY } }) });\n"
           "const body = BODY;\n" % json.dumps(body)) \
        + "let __e=null,OUT=null;\ntry{OUT=(()=>{\n" + code + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:OUT,err:__e}));\n"
    tmp = os.path.join(HERE, "_rr.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


DEFAULT = "rule_change_2026-08-26_melisa"
CASES = [
    ("no reason supplied -> original constant (back-compat)",
     {"row_ids": [1, 2]}, DEFAULT, True),
    ("reason supplied -> used verbatim",
     {"row_ids": [1], "removed_reason": "false_reply_empty_body"},
     "false_reply_empty_body", True),
    ("blank reason -> falls back to the constant",
     {"row_ids": [1], "removed_reason": "   "}, DEFAULT, True),
    ("non-string reason -> falls back",
     {"row_ids": [1], "removed_reason": 42}, DEFAULT, True),
    ("dry_run defaults TRUE when absent",
     {"row_ids": [1]}, DEFAULT, True),
    ("dry_run:false is honoured",
     {"row_ids": [1], "dry_run": False}, DEFAULT, False),
    ("over-long reason is truncated to 120",
     {"row_ids": [1], "removed_reason": "z" * 400}, "z" * 120, True),
]
for label, body, want_reason, want_dry in CASES:
    d, err = run(patched, body)
    out = (d or {}).get("out") or []
    got = (out[0] or {}).get("json") if out else {}
    good = (got.get("removed_reason") == want_reason) and (got.get("dry_run") is want_dry) \
        and not (d or {}).get("err")
    print("  [%s] %-50s reason=%r dry_run=%s"
          % ("ok " if good else "FAIL", label, str(got.get("removed_reason"))[:40],
             got.get("dry_run")))
    if err:
        print("        node error: %s" % err)
    ok = ok and good

# non-vacuity: the OLD code ignores a supplied reason
d, err = run(js, {"row_ids": [1], "removed_reason": "false_reply_empty_body"})
out = (d or {}).get("out") or []
old_reason = ((out[0] or {}).get("json") or {}).get("removed_reason") if out else None
good = old_reason == DEFAULT
print("  [%s] %-50s old code stamped %r" % ("ok " if good else "FAIL",
                                            "non-vacuity: old path ignores the reason",
                                            str(old_reason)[:40]))
ok = ok and good

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (8)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "retirement_backup_%d.json" % stamp), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: retirement_backup_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % RET, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % RET)
AN = {n["name"]: n for n in after["nodes"]}
live = AN["Build Items"]["parameters"]["jsCode"]
problems = []
if "body.removed_reason" not in live:
    problems.append("caller-supplied reason not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
if not after.get("active"):
    problems.append("RETIREMENT WORKFLOW IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  dnc_s4_retirement_removal versionId=%s active=%s nodes=%d"
      % (after.get("versionId"), after.get("active"), len(after["nodes"])))
sys.exit(1 if problems else 0)
