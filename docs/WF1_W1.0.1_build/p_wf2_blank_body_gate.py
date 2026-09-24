#!/usr/bin/env python3
"""WF-2: a reply whose body strips to nothing is not a reply. Same shape as WF-1's gate.

PLACEMENT. `Switch Event` output[1] is REPLIED and feeds `IF Nurture REPLIED` (the path to the
alert, the labels, the DNC row and the reply activity) and `IF Unknown Marker` (an infra warning
about campaign naming). The gate sits on the FIRST only: an unknown-marker warning is about the
campaign, not about the reply, and suppressing it would hide a real naming defect.

THE STRIP IS THE WHOLE TRICK. Measured on a live execution (51511): a naive `<[^>]+>` strip leaves
the contents of `<style>` behind, so the "text" of that reply began `P {margin-top:0;margin-bottom:0;}`.
An HTML-only empty reply would therefore look like 2,887 characters of content. So the strip removes
the BODIES of <style> and <script> first, then tags, then entities, then zero-width characters.

WHAT COUNTS AS REAL, decided and pinned by statics:
  * signature-only ('-- \\n Person-3426894b \\n VP Sales')  -> REAL. A signature is a message a human
    pressed send on, and no length rule can separate it from 'Thanks!'.
  * quoted-original-only                              -> REAL for now. Detecting it needs the
    quote-stripping family (`On ... wrote:`, fr/de/es) and deserves measurement first.
  * html that strips to nothing, nbsp/zero-width only, null/absent -> BLANK.

WF-2 has ZERO observed blank bodies; this is prophylactic, justified by shape-matching WF-1 rather
than by a measured WF-2 failure. Said plainly because the guard's value should not be overstated.
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


def code_only(js):
    return "\n".join(re.sub(r"//.*$", "", l) for l in js.splitlines()
                     if not l.strip().startswith("//"))


wf = n8n("/api/v1/workflows/%s" % WF2)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
C = wf.setdefault("connections", {})
if "Blank Body Gate" in N:
    sys.exit("blank-body gate already present")
for req in ("Switch Event", "IF Nurture REPLIED", "Normalize"):
    if req not in N:
        sys.exit("missing expected node: %s" % req)

# BLANK_BODY_GATE_V1 - the marker the linter looks for. Do not rename without updating the rule.
PRED = (
    "const __b = (() => { const n = (() => { try { return $('Normalize').item.json || {}; }"
    " catch (e) { return $json || {}; } })();"
    " return (n.reply && n.reply.body != null) ? n.reply.body"
    "      : (n.reply_body != null ? n.reply_body : (n.body != null ? n.body : '')); })();"
    " let __t = String(__b == null ? '' : __b);"
    " __t = __t.replace(/<(script|style)[\\s\\S]*?<\\/\\1>/gi, ' ');"
    " __t = __t.replace(/<[^>]*>/g, ' ');"
    " __t = __t.replace(/&nbsp;|&#160;|&#xa0;/gi, ' ');"
    " __t = __t.replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>');"
    " __t = __t.replace(/[\\u200b-\\u200d\\ufeff\\u00a0]/g, ' ');"
    " __t = __t.replace(/\\s+/g, ' ').trim();"
)
GATE_EXPR = "={{ (() => { /* BLANK_BODY_GATE_V1 */ " + PRED + " return __t.length > 0; })() }}"

SKIPPED = r"""
// BLANK_BODY_GATE_V1 - terminal. A reply whose body strips to nothing is not a human reply, so it
// earns no alert, no label, no DNC row, no task and no activity. Recorded rather than silent.
// WF-2 has no observed instance; this mirrors WF-1, where an accept artefact with message: ''
// produced all four consequences for a man who said nothing.
const n = (() => { try { return $('Normalize').item.json || {}; } catch (e) { return $json || {}; } })();
return [{ json: {
  __skipped: 'blank_reply_body',
  __event: n.event ?? null,
  __from: n.__reply_from ?? null,
  __campaign: n.campaign_name ?? n.campaign_id ?? null,
  __raw_body_len: String(((n.reply || {}).body) ?? '').length,
  __at: new Date().toISOString()
} }];
"""

BX, BY = N["IF Nurture REPLIED"]["position"]
wf["nodes"].append({
    "parameters": {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose",
                    "version": 1},
        "conditions": [{"id": "wf2-blankbody", "leftValue": GATE_EXPR, "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true",
                                     "singleValue": True}}],
        "combinator": "and"}, "options": {}},
    "name": "Blank Body Gate", "type": "n8n-nodes-base.if", "typeVersion": 2,
    "position": [BX - 200, BY]})
wf["nodes"].append({
    "parameters": {"jsCode": SKIPPED, "mode": "runOnceForAllItems"},
    "name": "Blank Body Skipped", "type": "n8n-nodes-base.code", "typeVersion": 2,
    "position": [BX - 200, BY + 180]})

sw = (C.get("Switch Event") or {}).get("main") or []
if len(sw) < 2:
    sys.exit("Switch Event has %d outputs" % len(sw))
if not [l for l in (sw[1] or []) if l and l.get("node") == "IF Nurture REPLIED"]:
    sys.exit("Switch Event[1] does not feed IF Nurture REPLIED; refusing to rewire blind")
sw[1] = [l for l in (sw[1] or []) if l.get("node") != "IF Nurture REPLIED"]
sw[1].append({"node": "Blank Body Gate", "type": "main", "index": 0})
C["Switch Event"]["main"] = sw
C["Blank Body Gate"] = {"main": [
    [{"node": "IF Nurture REPLIED", "type": "main", "index": 0}],
    [{"node": "Blank Body Skipped", "type": "main", "index": 0}]]}

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True
GATE_JS = PRED + " return __t.length > 0;"


def run(js, body):
    src = ("const NORM = { reply: { body: %s } };\n"
           "const $ = (nm) => ({ item: { json: NORM } });\nconst $json = NORM;\n"
           % json.dumps(body)) \
        + "let __e=null,OUT=null;\ntry{OUT=(()=>{\n" + js + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:OUT,err:__e}));\n"
    tmp = os.path.join(HERE, "_bb.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


CSS_EMPTY = ("<html><head><style>P {margin-top:0;margin-bottom:0;} "
             "body{font-family:Aptos}</style></head><body>"
             "<div>&nbsp;</div><br><div></div></body></html>")
CASES = [
    ("1  plain-text reply", "Hi Noah, sounds good - Tuesday works.", True),
    ("2  HTML with real text", "<div><p>Thanks, let's talk <b>Tuesday</b>.</p></div>", True),
    ("3  HTML that strips to nothing (CSS trap)", CSS_EMPTY, False),
    ("4  signature-only is REAL", "-- \nJohn Smith\nVP Sales\n+1 555 0100", True),
    ("5  quoted-original-only is REAL (for now)",
     "<div>On Tue, Noah wrote:<br>&gt; Are you going to Finovate?</div>", True),
    ("6a null body", None, False),
    ("6b empty string", "", False),
    ("7a whitespace only", "   \n\t  ", False),
    ("7b &nbsp; only", "<div>&nbsp;&nbsp;</div>", False),
    ("7c zero-width only", "​‍﻿", False),
]
for label, body, want in CASES:
    d, err = run(GATE_JS, body)
    got = (d or {}).get("out")
    good = (got is want) and not (d or {}).get("err")
    print("  [%s] %-44s -> %-5s (want %s)" % ("ok " if good else "FAIL", label, got, want))
    if err:
        print("        node error: %s" % err)
    ok = ok and good

# non-vacuity: a NAIVE strip passes case 3, which is the whole reason for the style/script removal
NAIVE = ("let __t = String(BODY == null ? '' : BODY).replace(/<[^>]*>/g,' ')"
         ".replace(/&nbsp;/gi,' ').replace(/\\s+/g,' ').trim(); return __t.length > 0;")
src = "const BODY = %s;\n" % json.dumps(CSS_EMPTY)
tmp = os.path.join(HERE, "_bb2.js")
with open(tmp, "w", encoding="utf-8") as f:
    f.write(src + "console.log(JSON.stringify((()=>{" + NAIVE + "})()));\n")
p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
os.remove(tmp)
naive = json.loads((p.stdout or "false").strip().splitlines()[-1])
print("  [%s] %-44s naive strip says %s" % ("ok " if naive is True else "FAIL",
                                            "non-vacuity: naive strip fails case 3", naive))
ok = ok and (naive is True)

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (11)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "wf2_backup_before_blank_body_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: wf2_backup_before_blank_body_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % WF2, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % WF2)
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in ("Blank Body Gate", "Blank Body Skipped"):
    if nm not in AN:
        problems.append("%s missing" % nm)
s1 = [l["node"] for l in (((AC.get("Switch Event") or {}).get("main") or [[]] * 2)[1] or [])]
if "IF Nurture REPLIED" in s1:
    problems.append("Switch Event[1] still feeds IF Nurture REPLIED directly")
if "Blank Body Gate" not in s1:
    problems.append("Switch Event[1] does not feed the gate (got %s)" % s1)
g = [[l["node"] for l in (b or [])] for b in ((AC.get("Blank Body Gate") or {}).get("main") or [])]
if g != [["IF Nurture REPLIED"], ["Blank Body Skipped"]]:
    problems.append("gate outputs wired as %s" % g)
if "BLANK_BODY_GATE_V1" not in json.dumps(AN["Blank Body Gate"]["parameters"], ensure_ascii=False):
    problems.append("linter marker missing from the gate")
if len(after["nodes"]) != len(ORIG["nodes"]) + 2:
    problems.append("node count %d expected %d" % (len(after["nodes"]), len(ORIG["nodes"]) + 2))
if not after.get("active"):
    problems.append("WF-2 IS INACTIVE after the PUT")
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p_ in problems:
    print("  -", p_)
print("  WF-2 versionId=%s active=%s nodes=%d" % (after.get("versionId"), after.get("active"),
                                                  len(after["nodes"])))
print("  Switch Event[1] -> %s" % s1)
sys.exit(1 if problems else 0)
