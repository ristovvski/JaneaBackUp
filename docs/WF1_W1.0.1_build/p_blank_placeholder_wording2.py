#!/usr/bin/env python3
"""Placeholder wording, second pass — name BOTH causes, and the common one first.

  '[no text - manually check, could be an attachment]'
    ->
  '[no text - manually check the inbox; could be an attachment or an empty connection-accept]'

WHY the change: Heath's conversation was verified in the HeyReach UI - his bubble is EMPTY, stamped
the same minute as Noah's invite. It is an accept surfacing as a reply, which is the COMMON cause.
"Attachment(s)" turned out to be HeyReach's list caption for any textless message, not evidence of a
file - so the first wording pointed the reader at the rarer cause and repeated the UI's own
misleading framing.

Three sites, same as the first pass: WF-1 `M7 Build.render()` (two returns, feeding both the alert
and the CRM note), WF-2 `Body Reply Alert`, WF-2 `Body Reply Activity`. Literal replacement only.
"""
import argparse
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
WF1 = "2jdjKM2NJr473GdA"
WF2 = "jp7rum9Z0YDJkQWv"

OLD_JS = "'[no text \\u2014 manually check, could be an attachment]'"
NEW_JS = ("'[no text \\u2014 manually check the inbox; could be an attachment or an empty "
          "connection-accept]'")
NEW = "[no text — manually check the inbox; could be an attachment or an empty connection-accept]"

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


def run(code, harness, pick):
    src = harness + "\nlet __e=null,OUT=null;\ntry{OUT=(()=>{\n" + code \
        + "\n})();}catch(e){__e=String(e.message||e);}\n" \
          "console.log(JSON.stringify({out:" + pick + ",err:__e}));\n"
    tmp = os.path.join(HERE, "_ph2.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


SITES = [(WF1, "M7 Build", 2), (WF2, "Body Reply Alert", 1), (WF2, "Body Reply Activity", 1)]
wfs, origs, news = {}, {}, {}
for wfid in (WF1, WF2):
    wfs[wfid] = n8n("/api/v1/workflows/%s" % wfid)
    origs[wfid] = copy.deepcopy(wfs[wfid])

total = 0
for wfid, node, expect in SITES:
    N = {n["name"]: n for n in wfs[wfid]["nodes"]}
    js = N[node]["parameters"]["jsCode"]
    if NEW in js:
        sys.exit("%s already carries the new wording" % node)
    c = js.count(OLD_JS)
    if c != expect:
        sys.exit("%s: expected %d occurrence(s) of the current placeholder, found %d"
                 % (node, expect, c))
    N[node]["parameters"]["jsCode"] = js.replace(OLD_JS, NEW_JS)
    news[(wfid, node)] = N[node]["parameters"]["jsCode"]
    total += c
    print("  %-22s %d occurrence(s) replaced" % (node, c))
print("total replacements: %d" % total)

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


mb = news[(WF1, "M7 Build")]
for label, msgs, pick, want in (
        ("WF-1 alert: blank", [OURS, BLANK], "OUT.json.alert_text", "Reply: " + NEW),
        ("WF-1 CRM note: blank", [OURS, BLANK], "OUT.json.reply_note", NEW),
        ("WF-1 alert: real reply unchanged", [OURS, REAL], "OUT.json.alert_text",
         "Reply: Sounds good, Tuesday works."),
        ("WF-1 attachment branch untouched",
         [OURS, {"is_reply": True, "message": "", "message_type": "ATTACHMENT"}],
         "OUT.json.reply_text", "[attachment]")):
    d, err = run(mb, h1(msgs), pick)
    got = str((d or {}).get("out") or "")
    good = (want in got) if pick != "OUT.json.reply_note" else (got == want)
    if label.endswith("untouched"):
        good = got == want
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, got[-78:]))
    ok = ok and good

ba = news[(WF2, "Body Reply Alert")]
for label, body, want in (
        ("WF-2 alert: blank", "", "Reply: " + NEW),
        ("WF-2 alert: HTML-only blank", "<style>p{margin:0}</style><div>&nbsp;</div>",
         "Reply: " + NEW),
        ("WF-2 alert: real reply unchanged", "<p>Looks good.</p>", "Reply: Looks good.")):
    d, err = run(ba, h2(body), "OUT[0].json.alert_text")
    got = str((d or {}).get("out") or "")
    good = want in got
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, got[-78:]))
    ok = ok and good

bact = news[(WF2, "Body Reply Activity")]
for label, body, want, unwanted in (
        ("WF-2 CRM note: blank", "", NEW, None),
        ("WF-2 CRM note: real keeps RAW body", "<p>Looks good.</p>", "<p>Looks good.</p>", NEW)):
    d, err = run(bact, h2(body), "OUT[0].json.__body.note")
    got = str((d or {}).get("out") or "")
    good = (want in got) and (unwanted is None or unwanted not in got)
    print("  [%s] %-38s %r" % ("ok " if good else "FAIL", label, got[:78]))
    ok = ok and good

# non-vacuity: the previous wording must be gone from every site
for (wfid, node), js in news.items():
    if "could be an attachment]" in js:
        print("  [FAIL] %s still carries the previous wording" % node)
        ok = False
print("  [ok ] previous wording absent from all three sites" if ok else "")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (10)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wfid, tag in ((WF1, "wf1"), (WF2, "wf2")):
    p = os.path.join(HERE, "%s_backup_before_wording2_%d.json" % (tag, stamp))
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(origs[wfid], indent=2, ensure_ascii=False))
    print("\nbackup: %s" % os.path.basename(p))
    sk = stripped_keys(wfs[wfid])
    if sk:
        print("stripped UI-only settings keys: %s" % sk)
    n8n("/api/v1/workflows/%s" % wfid, "PUT", put_body(wfs[wfid]))
    after = n8n("/api/v1/workflows/%s" % wfid)
    AN = {n["name"]: n for n in after["nodes"]}
    problems = []
    for w2, node, expect in SITES:
        if w2 != wfid:
            continue
        live = AN[node]["parameters"]["jsCode"]
        if live.count(NEW_JS) != expect:
            problems.append("%s: %d new occurrences, expected %d"
                            % (node, live.count(NEW_JS), expect))
        if OLD_JS in live:
            problems.append("%s: previous wording still live" % node)
    if len(after["nodes"]) != len(origs[wfid]["nodes"]):
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
print("\nboth causes named, common one first, in both receivers and both surfaces.")
