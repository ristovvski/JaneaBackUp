#!/usr/bin/env python3
"""Blank-body placeholder wording, both receivers, alert AND CRM note.

  '[empty message]'  ->  '[no text - manually check, could be an attachment]'   (em dash in the live
                                                                                 string)

WHY: an empty body is genuinely ambiguous. HeyReach's webhook carries no attachment marker at all,
its inbox API says TEXT for a message the UI labels "Attachment(s)", and no rule reachable from our
data separates the two. So the alert stops asserting and starts instructing: a human opens the
inbox. That is the whole fix - the gate is gone.

SITES (three edits, four surfaces):
  WF-1 `M7 Build.render()`   - one change, two surfaces: reply_text feeds the alert's `Reply:` row,
                               reply_note feeds `M7 Reply Activity`'s note.
  WF-2 `Body Reply Alert`    - has no reply line at all today; gains one, same shape as WF-1.
  WF-2 `Body Reply Activity` - `if (n.reply.body)` omits the line entirely on a blank body, so the
                               timeline says nothing. Now it says the same as the alert.

NOT TOUCHED: `M6 Build`, which also renders '[empty message]' - that is OUR OWN sent message on the
message_sent path, and "could be an attachment, manually check" is the wrong instruction for it.

The alert excerpt tests blankness on the SAME stripped text it displays. Testing the raw body while
displaying stripped text is how you get an alert that says `Reply: ` followed by nothing.
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

PH = "[no text — manually check, could be an attachment]"
PH_JS = "'[no text \\u2014 manually check, could be an attachment]'"

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


def run(code, harness, pick="OUT"):
    src = harness + "\nlet __e=null,OUT=null;\ntry{OUT=(()=>{\n" + code \
        + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:" + pick + ",err:__e}));\n"
    tmp = os.path.join(HERE, "_ph.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


# ================================================================== WF-1
wf1 = n8n("/api/v1/workflows/%s" % WF1)
O1 = copy.deepcopy(wf1)
N1 = {n["name"]: n for n in wf1["nodes"]}
mb = N1["M7 Build"]["parameters"]["jsCode"]
if PH in mb:
    sys.exit("WF-1 wording already applied")
if mb.count("return '[empty message]';") != 2:
    sys.exit("M7 Build: expected exactly 2 '[empty message]' returns, found %d"
             % mb.count("return '[empty message]';"))
# comment line mentioning the old string is prose; only the two RETURNS change
mb_new = mb.replace("return '[empty message]';", "return " + PH_JS + ";")
N1["M7 Build"]["parameters"]["jsCode"] = mb_new

# ================================================================== WF-2
wf2 = n8n("/api/v1/workflows/%s" % WF2)
O2 = copy.deepcopy(wf2)
N2 = {n["name"]: n for n in wf2["nodes"]}
ba = N2["Body Reply Alert"]["parameters"]["jsCode"]
if "Reply: " in ba:
    sys.exit("WF-2 alert already carries a reply line")
ANCHOR2 = ("const alert_text = __headline + (__rows.length ? "
           "'\\n*Details:*\\n' + __rows.join('\\n') : '');")
if ANCHOR2 not in ba:
    sys.exit("WF-2 Body Reply Alert anchor not found verbatim")
ADD2 = """// WHAT was said, not only THAT something arrived - matching WF-1. Blankness is tested on the
// SAME stripped text that is displayed: testing the raw body while showing stripped text produces
// an alert reading 'Reply: ' followed by nothing.
const __strip = (s) => String(s == null ? '' : s)
  .replace(/<(script|style)[\\s\\S]*?<\\/\\1>/gi, ' ')
  .replace(/<[^>]*>/g, ' ')
  .replace(/&nbsp;|&#160;/gi, ' ')
  .replace(/\\s+/g, ' ')
  .trim();
const __rtxt = __strip((n.reply || {}).body);
__rows.push('Reply: ' + (__rtxt
  ? (esc(__rtxt.slice(0, 120)) + (__rtxt.length > 120 ? '\\u2026' : ''))
  : """ + PH_JS + """));
const alert_text = __headline + (__rows.length ? '\\n*Details:*\\n' + __rows.join('\\n') : '');"""
ba_new = ba.replace(ANCHOR2, ADD2, 1)
N2["Body Reply Alert"]["parameters"]["jsCode"] = ba_new

bact = N2["Body Reply Activity"]["parameters"]["jsCode"]
OLD3 = "if (n.reply.body) noteParts.push(String(n.reply.body).slice(0, 8000));"
if OLD3 not in bact:
    sys.exit("WF-2 Body Reply Activity body line not found verbatim")
NEW3 = ("""// A blank body used to omit this line entirely, so the CRM timeline said nothing while the
// alert said something. Same placeholder in both surfaces now. The RAW body is still stored when
// there is one - the strip decides only whether there is text, never what gets recorded.
if (String(n.reply.body == null ? '' : n.reply.body)
      .replace(/<(script|style)[\\s\\S]*?<\\/\\1>/gi, ' ').replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;|&#160;/gi, ' ').replace(/\\s+/g, ' ').trim())
  noteParts.push(String(n.reply.body).slice(0, 8000));
else noteParts.push(""" + PH_JS + """);""")
N2["Body Reply Activity"]["parameters"]["jsCode"] = bact.replace(OLD3, NEW3, 1)

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True
OURS = {"is_reply": False, "message": "Hi Heath, great to connect."}
BLANK = {"is_reply": True, "message": ""}
REAL = {"is_reply": True, "message": "Sounds good, Tuesday works."}
LONG = {"is_reply": True, "message": "y" * 400}

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


for label, msgs, want in (
        ("WF-1 alert: blank reply", [OURS, BLANK], "Reply: " + PH),
        ("WF-1 alert: real reply", [OURS, REAL], "Reply: Sounds good, Tuesday works."),
        ("WF-1 alert: 120-char truncation", [OURS, LONG], "Reply: " + "y" * 120 + "…")):
    d, err = run(mb_new, h1(msgs), "OUT.json.alert_text")
    txt = (d or {}).get("out") or ""
    good = want in txt
    print("  [%s] %-40s %r" % ("ok " if good else "FAIL", label, str(txt)[-72:]))
    ok = ok and good

for label, msgs, want in (
        ("WF-1 CRM note: blank reply", [OURS, BLANK], PH),
        ("WF-1 CRM note: real reply", [OURS, REAL], "Sounds good, Tuesday works.")):
    d, err = run(mb_new, h1(msgs), "OUT.json.reply_note")
    note = (d or {}).get("out") or ""
    good = note == want
    print("  [%s] %-40s %r" % ("ok " if good else "FAIL", label, str(note)[:72]))
    ok = ok and good

# attachment / voice branches must be untouched (dead today, but not silently altered)
d, err = run(mb_new, h1([OURS, {"is_reply": True, "message": "", "message_type": "ATTACHMENT"}]),
             "OUT.json.reply_text")
good = (d or {}).get("out") == "[attachment]"
print("  [%s] %-40s %r" % ("ok " if good else "FAIL", "WF-1 attachment branch unchanged",
                           (d or {}).get("out")))
ok = ok and good


def h2(body):
    n = {"reply": {"body": body, "subject": "RE: hi", "received_at": "2026-09-11T00:00:00Z"},
         "lead": {"full_name": "Person-d86d9627", "email": "pii-78fa258a@example.invalid", "title": "VP", "company": "Akoya",
                  "website": None, "linkedin": None},
         "campaign_name": "C", "sender_inbox": "noah@x", "reply_category": None,
         "__reply_class": "lead"}
    return ("const CFG={pipedrive_base:'https://pd', sl_inbox_base:'https://sl/', fields:{}};\n"
            "const NORM=%s;\nconst $json={__lead_id:'L',__person_id:1};\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM : {} } });\n"
            % json.dumps(n))


for label, body, want in (
        ("WF-2 alert: blank body", "", "Reply: " + PH),
        ("WF-2 alert: HTML-only blank", "<style>p{margin:0}</style><div>&nbsp;</div>",
         "Reply: " + PH),
        ("WF-2 alert: real reply", "<p>Looks good, see you Tuesday.</p>",
         "Reply: Looks good, see you Tuesday."),
        ("WF-2 alert: null body", None, "Reply: " + PH)):
    d, err = run(ba_new, h2(body), "OUT[0].json.alert_text")
    txt = (d or {}).get("out") or ""
    good = want in txt
    print("  [%s] %-40s %r" % ("ok " if good else "FAIL", label, str(txt)[-72:]))
    if err:
        print("        %s" % err)
    ok = ok and good

bact_new = N2["Body Reply Activity"]["parameters"]["jsCode"]
for label, body, want, unwanted in (
        ("WF-2 CRM note: blank body", "", PH, None),
        ("WF-2 CRM note: HTML-only blank", "<div>&nbsp;</div>", PH, None),
        ("WF-2 CRM note: real reply keeps RAW body", "<p>Looks good.</p>", "<p>Looks good.</p>",
         PH)):
    h = h2(body).replace("const $json={__lead_id:'L',__person_id:1};",
                         "const $json={__lead_id:'L',__person_id:1,__deal_id:null};")
    d, err = run(bact_new, h, "OUT[0].json.__body.note")
    note = (d or {}).get("out") or ""
    good = (want in note) and (unwanted is None or unwanted not in note)
    print("  [%s] %-40s %r" % ("ok " if good else "FAIL", label, str(note)[:72]))
    if err:
        print("        %s" % err)
    ok = ok and good

# non-vacuity
d, err = run(mb, h1([OURS, BLANK]), "OUT.json.reply_text")
good = (d or {}).get("out") == "[empty message]"
print("  [%s] %-40s old WF-1 said %r" % ("ok " if good else "FAIL", "non-vacuity: WF-1 old string",
                                         (d or {}).get("out")))
ok = ok and good
d, err = run(ba, h2(""), "OUT[0].json.alert_text")
good = "Reply:" not in ((d or {}).get("out") or "")
print("  [%s] %-40s old WF-2 alert had no Reply line" % ("ok " if good else "FAIL",
                                                         "non-vacuity: WF-2 old alert"))
ok = ok and good

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (16)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wf, orig, wfid, tag in ((wf1, O1, WF1, "wf1"), (wf2, O2, WF2, "wf2")):
    p = os.path.join(HERE, "%s_backup_before_wording_%d.json" % (tag, stamp))
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
    if tag == "wf1":
        js = AN["M7 Build"]["parameters"]["jsCode"]
        if js.count("return '[no text") != 2:
            problems.append("expected 2 new-placeholder returns, found %d"
                            % js.count("return '[no text"))
        if "return '[empty message]';" in js:
            problems.append("old placeholder still returned")
        if "'[attachment]'" not in js:
            problems.append("attachment branch was altered")
    else:
        if "Reply: " not in AN["Body Reply Alert"]["parameters"]["jsCode"]:
            problems.append("WF-2 alert reply line not live")
        if "no text" not in AN["Body Reply Activity"]["parameters"]["jsCode"]:
            problems.append("WF-2 activity placeholder not live")
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
print("\nboth receivers say the same thing, in both surfaces.")
