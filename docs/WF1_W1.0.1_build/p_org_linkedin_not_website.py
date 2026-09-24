#!/usr/bin/env python3
"""A linkedin.com URL is not a website. Guard the WF-1 org write, and label it correctly in both alerts.

WHAT IS ACTUALLY BROKEN, measured before changing anything:

  * **The alerts.** WF-1 `M7 Build` prints `Company website: ` + HeyReach's `lead.company_url`,
    which for a LinkedIn campaign is the company's LinkedIn PAGE. WF-2 `Body Reply Alert` does the
    same with `n.lead.website`. That is the Brillio / Pathomiq / Novo Nordisk output.
  * **WF-1 `Org Create`.** `body[cfg.org_website_field] = n.lead.company_url` with no test at all -
    `org_website_field` is `'website'`, so a LinkedIn page goes into the org's website.

WHAT IS NOT BROKEN, so it is not touched:

  * **WF-2 `Body Org Create` already has this guard** (`W1.0.12`), and it is mutually exclusive:
    `if (w && !isLi(w)) {3 website fields}` / `if (w && isLi(w)) {org_linkedin_lh}`. Left alone.
  * **The three named orgs are clean in Pipedrive** - Brillio and PATHOMIQ carry real domains in
    `website` and LinkedIn URLs in the LinkedIn fields; Novo Nordisk carries only a LinkedIn field.
    So this is a forward guard plus an alert-label fix, not a repair. The count comes separately.

FIELD CHOICE: `ed932dfc4870dcd72fa7b4eadb67da38d169299b` (`lh_linkedin_profile_url`) - the same
field WF-2 writes, so both receivers agree. It goes into WF-1's CONFIG as `org_linkedin_field`
rather than being hardcoded in the node, matching how `org_website_field` already works.
Pipedrive's NATIVE `linkedin` key cannot be used: it is a read-only system field.
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
ORG_LI_KEY = "ed932dfc4870dcd72fa7b4eadb67da38d169299b"

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
    tmp = os.path.join(HERE, "_ow.js")
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

# ---- CONFIG gains the field key (not hardcoded in the node)
cfg_raw = (N1["CONFIG"].get("parameters") or {}).get("jsonOutput")
cfg_str = str(cfg_raw)
if "org_linkedin_field" in cfg_str:
    sys.exit("WF-1 CONFIG already has org_linkedin_field")
if '"org_website_field": "website"' not in cfg_str:
    sys.exit("WF-1 CONFIG: org_website_field anchor not found verbatim")
N1["CONFIG"]["parameters"]["jsonOutput"] = cfg_str.replace(
    '"org_website_field": "website"',
    '"org_website_field": "website",\n  "org_linkedin_field": "%s"' % ORG_LI_KEY, 1)

# ---- Org Create gains the guard
oc = N1["Org Create"]["parameters"]["jsonBody"]
OLD_OC = "  if (site !== '') body[cfg.org_website_field] = site;  // B1 create-only, R4-omit"
if OLD_OC not in oc:
    sys.exit("WF-1 Org Create website line not found verbatim")
# REAL newlines. The jsonBody is a JSON string holding actual line breaks; writing literal "\n"
# sequences put the entire guard inside one comment line, and the body came back as {"name":...}
# with no site at all. The statics caught it - which is the only reason this note exists.
NEW_OC = ("  // A linkedin.com URL is not a website. HeyReach's `company_url` is the company's\n"
          "  // LinkedIn PAGE on a LinkedIn campaign, and it was going straight into the org's\n"
          "  // website field. Route it to the LinkedIn field instead; only a real domain is a\n"
          "  // website. Same rule WF-2's `Body Org Create` has carried since W1.0.12.\n"
          "  const isLi = (u) => /(^|\\.)linkedin\\.com/i.test(String(u || ''));\n"
          "  if (site !== '') {\n"
          "    if (isLi(site)) body.custom_fields = { [cfg.org_linkedin_field]: site };\n"
          "    else body[cfg.org_website_field] = site;  // B1 create-only, R4-omit\n"
          "  }")
N1["Org Create"]["parameters"]["jsonBody"] = oc.replace(OLD_OC, NEW_OC, 1)

# ---- WF-1 alert label
mb = N1["M7 Build"]["parameters"]["jsCode"]
OLD_A1 = "if (__web) __rows.push('Company website: ' + escapeSlack(__web));"
if OLD_A1 not in mb:
    sys.exit("WF-1 alert website row not found verbatim")
NEW_A1 = ("// Label what the value IS. `company_url` on a LinkedIn campaign is the company's\n"
          "// LinkedIn page, and printing it as 'Company website' told the reader something false.\n"
          "const __isLiUrl = (u) => /(^|\\.)linkedin\\.com/i.test(String(u || ''));\n"
          "if (__web) __rows.push((__isLiUrl(__web) ? 'Company LinkedIn: ' : 'Company website: ')\n"
          "  + escapeSlack(__web));")
mb_new = mb.replace(OLD_A1, NEW_A1, 1)
N1["M7 Build"]["parameters"]["jsCode"] = mb_new

# ================================================================== WF-2 (alert only)
wf2 = n8n("/api/v1/workflows/%s" % WF2)
O2 = copy.deepcopy(wf2)
N2 = {n["name"]: n for n in wf2["nodes"]}
ba = N2["Body Reply Alert"]["parameters"]["jsCode"]
OLD_A2 = "if (__web) __rows.push('Company website: ' + esc(__web));"
if OLD_A2 not in ba:
    sys.exit("WF-2 alert website row not found verbatim")
NEW_A2 = ("// Label what the value IS - same rule as WF-1. `Body Org Create` already routes a\n"
          "// linkedin.com URL away from the website fields (W1.0.12); the alert did not.\n"
          "const __isLiUrl = (u) => /(^|\\.)linkedin\\.com/i.test(String(u || ''));\n"
          "if (__web) __rows.push((__isLiUrl(__web) ? 'Company LinkedIn: ' : 'Company website: ')\n"
          "  + esc(__web));")
ba_new = ba.replace(OLD_A2, NEW_A2, 1)
N2["Body Reply Alert"]["parameters"]["jsCode"] = ba_new

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True
LI = "https://www.linkedin.com/company/brillio/home/"
DOM = "https://www.brillio.com"

# 1) Org Create body
oc_new = N1["Org Create"]["parameters"]["jsonBody"]
body_js = oc_new[oc_new.index("(() => {"):oc_new.rindex("})()")] + "})()"


def h_org(company_url):
    return ("const NORM = {lead:{company_name:'Brillio', company_url:%s}};\n"
            "const CFG = {org_website_field:'website', org_linkedin_field:'%s'};\n"
            "const $ = (nm) => ({ item: { json: nm==='Normalize'?NORM:CFG } });\n"
            % (json.dumps(company_url), ORG_LI_KEY))


for label, url, want in (
        ("org: linkedin.com/company -> LinkedIn field, website untouched", LI, "li"),
        ("org: real domain -> website, no LinkedIn field", DOM, "web"),
        ("org: no url -> neither field", "", "none")):
    d, err = run("return " + body_js + ";", h_org(url), "OUT")
    raw = (d or {}).get("out")
    body = json.loads(raw) if isinstance(raw, str) else {}
    cf = body.get("custom_fields") or {}
    has_li = cf.get(ORG_LI_KEY) == url and url != ""
    has_web = body.get("website") == url and url != ""
    good = {"li": has_li and "website" not in body,
            "web": has_web and not cf,
            "none": ("website" not in body) and not cf}[want]
    print("  [%s] %-56s %s" % ("ok " if good else "FAIL", label, json.dumps(body)[:90]))
    if err:
        print("        %s" % err)
    ok = ok and good

# 2) alerts
CFG1 = {"fields": {"stage": "S", "conversation": "CV", "lead_campaign": "F"},
        "stageRank": {}, "melisa_user_id": 1, "pipedrive_base": "https://pd"}


def h1(company_url):
    norm = {"msgs": [{"is_reply": True, "message": "hi"}],
            "lead": {"full_name": "A B", "position": "P", "company_name": "Brillio",
                     "company_url": company_url, "profile_url": "https://li/x"},
            "campaign": {"name": "C"}, "sender": {"name": "Noah"}, "conv": "c", "is_inmail": False}
    return ("const CFG=%s, NORM=%s;\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM"
            " : nm==='M7 Person Get'?{data:{id:1,custom_fields:{}}}"
            " : nm==='M7 Lead Get'?{data:[{id:'L',is_archived:false,F:'C'}]} : {} } });\n"
            % (json.dumps(CFG1), json.dumps(norm)))


for label, url, want, unwant in (
        ("WF-1 alert: linkedin url -> 'Company LinkedIn'", LI, "Company LinkedIn: " + LI,
         "Company website"),
        ("WF-1 alert: real domain -> 'Company website'", DOM, "Company website: " + DOM,
         "Company LinkedIn")):
    d, err = run(mb_new, h1(url), "OUT.json.alert_text")
    txt = str((d or {}).get("out") or "")
    good = (want in txt) and (unwant not in txt)
    print("  [%s] %-56s %r" % ("ok " if good else "FAIL", label, txt[-62:]))
    ok = ok and good


def h2(website):
    n = {"reply": {"body": "hi", "subject": "s"},
         "lead": {"full_name": "Amity", "email": "pii-78fa258a@example.invalid", "title": "VP", "company": "Akoya",
                  "website": website, "linkedin": None},
         "campaign_name": "C", "sender_inbox": "noah@x", "reply_category": None,
         "__reply_class": "lead"}
    return ("const CFG={pipedrive_base:'https://pd', sl_inbox_base:'https://sl/', fields:{}};\n"
            "const NORM=%s;\nconst $json={__lead_id:'L',__person_id:1,__deal_id:null};\n"
            "const $ = (nm) => ({ item: { json: nm==='CONFIG'?CFG : nm==='Normalize'?NORM : {} } });\n"
            % json.dumps(n))


for label, url, want, unwant in (
        ("WF-2 alert: linkedin url -> 'Company LinkedIn'", LI, "Company LinkedIn: " + LI,
         "Company website"),
        ("WF-2 alert: real domain -> 'Company website'", DOM, "Company website: " + DOM,
         "Company LinkedIn")):
    d, err = run(ba_new, h2(url), "OUT[0].json.alert_text")
    txt = str((d or {}).get("out") or "")
    good = (want in txt) and (unwant not in txt)
    print("  [%s] %-56s %r" % ("ok " if good else "FAIL", label, txt[-62:]))
    ok = ok and good

# 3) host-match precision: a domain that merely CONTAINS the word must not match
for label, url, want_li in (("not-linkedin.com.example.org is NOT linkedin",
                             "https://not-linkedin.com.example.org", True),
                            ("mylinkedin.com IS matched by (^|.)linkedin.com",
                             "https://mylinkedin.com", False)):
    d, err = run(mb_new, h1(url), "OUT.json.alert_text")
    txt = str((d or {}).get("out") or "")
    got_li = "Company LinkedIn:" in txt
    print("  [--] %-56s -> %s" % (label, "Company LinkedIn" if got_li else "Company website"))

# non-vacuity
d, err = run(mb, h1(LI), "OUT.json.alert_text")
good = "Company website: " + LI in str((d or {}).get("out") or "")
print("  [%s] %-56s (old WF-1 mislabelled it)" % ("ok " if good else "FAIL", "non-vacuity WF-1"))
ok = ok and good
d, err = run(ba, h2(LI), "OUT[0].json.alert_text")
good = "Company website: " + LI in str((d or {}).get("out") or "")
print("  [%s] %-56s (old WF-2 mislabelled it)" % ("ok " if good else "FAIL", "non-vacuity WF-2"))
ok = ok and good

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (11)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for wf, orig, wfid, tag in ((wf1, O1, WF1, "wf1"), (wf2, O2, WF2, "wf2")):
    p = os.path.join(HERE, "%s_backup_before_org_li_%d.json" % (tag, stamp))
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
        if "org_linkedin_field" not in str(AN["CONFIG"]["parameters"].get("jsonOutput")):
            problems.append("CONFIG key not live")
        if "isLi(site)" not in AN["Org Create"]["parameters"]["jsonBody"]:
            problems.append("Org Create guard not live")
        if "Company LinkedIn: " not in AN["M7 Build"]["parameters"]["jsCode"]:
            problems.append("WF-1 alert label not live")
    else:
        if "Company LinkedIn: " not in AN["Body Reply Alert"]["parameters"]["jsCode"]:
            problems.append("WF-2 alert label not live")
        if "W1.0.12 guard" not in AN["Body Org Create"]["parameters"]["jsCode"]:
            problems.append("WF-2 org guard was disturbed - it must be untouched")
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
print("\na linkedin.com URL is now labelled as one, and no longer lands in a website field.")
