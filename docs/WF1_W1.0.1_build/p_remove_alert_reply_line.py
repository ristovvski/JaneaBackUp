#!/usr/bin/env python3
"""Remove the `Reply:` line from the SLACK ALERT in both receivers. Keep it in the CRM note.

WF-1 `M7 Build`        - drop the __excerpt block that pushes 'Reply: ...' into __rows.
                         `reply_note` is computed separately from render() and is NOT touched, so
                         the activity note keeps the text and the placeholder.
WF-2 `Body Reply Alert`- drop the __strip/__rtxt block that pushes 'Reply: ...' into __rows.
                         `Body Reply Activity` is a different node and is NOT touched.

Nothing else changes. The removal is line-span based rather than a verbatim block match: it finds
the start statement, walks back over the contiguous comment lines that belong to it, and ends at the
statement's closing line - then asserts the result contains no `Reply: ` at all and still executes.
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
WF2 = "jp7rum9Z0YDJkQWv"
PH = "[no text — manually check the inbox; could be an attachment or an empty connection-accept]"
# The SOURCE stores the em dash escaped. Asserting on the rendered form against jsCode is how the
# first deploy pass false-alarmed after WF-1 had already been written correctly - the third
# representation mismatch of this kind today. Assert on what is actually in the file.
PH_SRC = "[no text \\u2014 manually check the inbox; could be an attachment or an empty connection-accept]"

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


def cut(js, start_pat, end_pat, label):
    """Remove [contiguous leading comments + start line .. end line] inclusive."""
    lines = js.splitlines()
    si = next((i for i, l in enumerate(lines) if re.search(start_pat, l)), None)
    if si is None:
        # already cut - the first deploy pass wrote WF-1 and then aborted on a bad assertion,
        # so this must be resumable rather than fatal
        print("  %s: block already absent, nothing to remove" % label)
        return None
    ei = next((i for i in range(si, len(lines)) if re.search(end_pat, lines[i])), None)
    if ei is None:
        sys.exit("%s: end pattern %r not found after the start" % (label, end_pat))
    # walk back over the comment block that introduces this statement
    b = si
    while b > 0 and lines[b - 1].strip().startswith("//"):
        b -= 1
    removed = lines[b:ei + 1]
    print("  %s: removing lines %d-%d (%d lines)" % (label, b + 1, ei + 1, len(removed)))
    for l in removed:
        print("     - %s" % l[:104])
    return "\n".join(lines[:b] + lines[ei + 1:])


def run(code, harness, pick):
    src = harness + "\nlet __e=null,OUT=null;\ntry{OUT=(()=>{\n" + code \
        + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:" + pick + ",err:__e}));\n"
    tmp = os.path.join(HERE, "_rl.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


wf1 = n8n("/api/v1/workflows/%s" % WF1)
O1 = copy.deepcopy(wf1)
N1 = {n["name"]: n for n in wf1["nodes"]}
mb_old = N1["M7 Build"]["parameters"]["jsCode"]
print("--- WF-1 M7 Build ---")
mb_new = cut(mb_old, r"const __excerpt = String\(reply_text", r"^\s*\}\s*$", "M7 Build")
WF1_CHANGED = mb_new is not None
if mb_new is None:
    mb_new = mb_old
N1["M7 Build"]["parameters"]["jsCode"] = mb_new

wf2 = n8n("/api/v1/workflows/%s" % WF2)
O2 = copy.deepcopy(wf2)
N2 = {n["name"]: n for n in wf2["nodes"]}
ba_old = N2["Body Reply Alert"]["parameters"]["jsCode"]
print("\n--- WF-2 Body Reply Alert ---")
ba_new = cut(ba_old, r"const __strip = \(s\) =>", r"connection-accept\]'\)\);", "Body Reply Alert")
WF2_CHANGED = ba_new is not None
if ba_new is None:
    ba_new = ba_old
N2["Body Reply Alert"]["parameters"]["jsCode"] = ba_new

for label, js in (("M7 Build", mb_new), ("Body Reply Alert", ba_new)):
    if "Reply: " in js:
        sys.exit("%s still contains a 'Reply: ' literal after the cut" % label)

print("\n--- statics ---")
ok = True
OURS = {"is_reply": False, "message": "Hi Heath, great to connect."}
BLANK = {"is_reply": True, "message": ""}
REAL = {"is_reply": True, "message": "Sounds good, Tuesday works."}
CFG1 = {"fields": {"stage": "S", "conversation": "CV", "lead_campaign": "F"},
        "stageRank": {}, "melisa_user_id": 1, "pipedrive_base": "https://pd"}


def h1(msgs):
    norm = {"msgs": msgs, "lead": {"full_name": "Person-8768306e", "position": "President",
                                   "company_name": "Circle", "profile_url": "https://li/x"},
            "campaign": {"name": "C"}, "sender": {"name": "Noah"}, "conv": "c", "is_inmail": False}
    return ("const CFG=%s, NORM=%s;\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM"
            " : nm==='M7 Person Get'?{data:{id:1,custom_fields:{}}}"
            " : nm==='M7 Lead Get'?{data:[{id:'L',is_archived:false,F:'C'}]} : {} } });\n"
            % (json.dumps(CFG1), json.dumps(norm)))


def h2(body):
    n = {"reply": {"body": body, "subject": "RE: hi", "received_at": "2026-09-11T00:00:00Z"},
         "lead": {"full_name": "Person-d86d9627", "email": "pii-78fa258a@example.invalid", "title": "VP", "company": "Akoya",
                  "website": None, "linkedin": None},
         "campaign_name": "C", "sender_inbox": "noah@x", "reply_category": None,
         "__reply_class": "lead"}
    return ("const CFG={pipedrive_base:'https://pd', sl_inbox_base:'https://sl/', fields:{}};\n"
            "const NORM=%s;\nconst $json={__lead_id:'L',__person_id:1,__deal_id:null};\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM : {} } });\n"
            % json.dumps(n))


# --- ALERT BODIES: no Reply line, for blank or real
for label, msgs in (("WF-1 alert, blank reply", [OURS, BLANK]),
                    ("WF-1 alert, real reply", [OURS, REAL])):
    d, err = run(mb_new, h1(msgs), "OUT.json.alert_text")
    txt = str((d or {}).get("out") or "")
    good = bool(txt) and "Reply:" not in txt and not (d or {}).get("err")
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, txt[-74:]))
    if err:
        print("        %s" % err)
    ok = ok and good

for label, body in (("WF-2 alert, blank body", ""), ("WF-2 alert, real reply", "<p>Hi.</p>")):
    d, err = run(ba_new, h2(body), "OUT[0].json.alert_text")
    txt = str((d or {}).get("out") or "")
    good = bool(txt) and "Reply:" not in txt and not (d or {}).get("err")
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, txt[-74:]))
    if err:
        print("        %s" % err)
    ok = ok and good

# --- CRM NOTES: unchanged
for label, msgs, want in (("WF-1 note, blank reply", [OURS, BLANK], PH),
                          ("WF-1 note, real reply", [OURS, REAL], "Sounds good, Tuesday works.")):
    d, err = run(mb_new, h1(msgs), "OUT.json.reply_note")
    got = str((d or {}).get("out") or "")
    good = got == want
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, got[:74]))
    ok = ok and good

bact = N2["Body Reply Activity"]["parameters"]["jsCode"]
for label, body, want in (("WF-2 note, blank body", "", PH),
                          ("WF-2 note, real reply", "<p>Hi.</p>", "<p>Hi.</p>")):
    d, err = run(bact, h2(body), "OUT[0].json.__body.note")
    got = str((d or {}).get("out") or "")
    good = want in got
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, got[:74]))
    ok = ok and good

# --- the alert still renders everything else it used to
d, err = run(mb_new, h1([OURS, REAL]), "OUT.json.alert_text")
txt = str((d or {}).get("out") or "")
good = ("Person-8768306e" in txt) and ("Company: Circle" in txt) and ("*Details:*" in txt)
print("  [%s] %-38s %r" % ("ok " if good else "FAIL", "WF-1 alert keeps its Details block",
                           txt[:74]))
ok = ok and good

# --- non-vacuity: the CURRENT live code does carry a Reply line
d, err = run(mb_old, h1([OURS, REAL]), "OUT.json.alert_text")
good = ("Reply:" in str((d or {}).get("out") or "")) or not WF1_CHANGED
print("  [%s] %-38s (live WF-1 alert carries it today)" % ("ok " if good else "FAIL",
                                                           "non-vacuity WF-1"))
ok = ok and good
d, err = run(ba_old, h2("<p>Hi.</p>"), "OUT[0].json.alert_text")
good = ("Reply:" in str((d or {}).get("out") or "")) or not WF2_CHANGED
print("  [%s] %-38s (live WF-2 alert carries it today)" % ("ok " if good else "FAIL",
                                                           "non-vacuity WF-2"))
ok = ok and good

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (11)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wf, orig, wfid, tag, node in ((wf1, O1, WF1, "wf1", "M7 Build"),
                                  (wf2, O2, WF2, "wf2", "Body Reply Alert")):
    p = os.path.join(HERE, "%s_backup_before_alert_line_removal_%d.json" % (tag, stamp))
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(orig, indent=2, ensure_ascii=False))
    print("\nbackup: %s" % os.path.basename(p))
    sk = stripped_keys(wf)
    if sk:
        print("stripped UI-only settings keys: %s" % sk)
    n8n("/api/v1/workflows/%s" % wfid, "PUT", put_body(wf))
    after = n8n("/api/v1/workflows/%s" % wfid)
    AN = {n["name"]: n for n in after["nodes"]}
    problems = []
    if "Reply: " in AN[node]["parameters"]["jsCode"]:
        problems.append("%s still carries a Reply line" % node)
    note_node = "M7 Build" if tag == "wf1" else "Body Reply Activity"
    if PH_SRC not in AN[note_node]["parameters"]["jsCode"]:
        problems.append("%s lost the CRM placeholder" % note_node)
    if len(after["nodes"]) != len(orig["nodes"]):
        problems.append("node count changed")
    if not after.get("active"):
        problems.append("WORKFLOW IS INACTIVE after the PUT")
    print("  %s: %s  versionId=%s active=%s nodes=%d"
          % (tag.upper(), "CLEAN" if not problems else "PROBLEMS", after.get("versionId"),
             after.get("active"), len(after["nodes"])))
    for pr in problems:
        print("    -", pr)
    if problems:
        sys.exit(1)
print("\nalerts carry no reply text; the CRM note still does.")
