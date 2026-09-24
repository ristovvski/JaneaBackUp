#!/usr/bin/env python3
"""TEAM ALERT FORMAT (Melisa): add a Details block, drop the Smartlead link. WF-1 + WF-2.

Rule that shapes the whole thing: a missing field OMITS ITS LINE. Never "None", never "?", never an
empty value after a label. That is the pre-rendered-wrong-text lesson - an alert that prints
"Company: None" is worse than one that says nothing, because it looks like an answer.

Sources, all already resolved in the execution - no extra HTTP call:
  WF-1  Normalize.lead has full_name / company_name / company_url / profile_url natively.
  WF-2  Normalize.lead has full_name / company / website / linkedin, and where those are null the
        person record's custom fields (linkedin_profile, linkedin_lh, company_lh) are read from
        `R Person Verify` in a try/catch, since that node is not on every path.

The Smartlead link is removed from the TEAM alert only. Ops-channel alerts are untouched: they are
built by different nodes entirely (`Ops Warn *`), so nothing here can reach them.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF1, WF2 = "2jdjKM2NJr473GdA", "jp7rum9Z0YDJkQWv"

# ---------------------------------------------------------------- WF-2
W2_OLD = """const alert_text = '\\ud83d\\udcac ' + who + paren + ' \\u00b7 ' + esc(n.campaign_name)
  + ' \\u00b7 via ' + esc(n.sender_inbox) + ' \\u2014 ' + link + slLink
  + ' \\u00b7 \\u2709\\ufe0f ' + esc(n.lead.email);"""
W2_NEW = """// Melisa's format: headline (built above, Smartlead link removed) + a Details block.
// person custom fields are a fallback for what Smartlead did not carry; the node is not on every
// path, so the lookup is guarded rather than assumed.
const __pcf = (() => {
  try { return ($('R Person Verify').item.json.data || {}).custom_fields || {}; }
  catch (e) { return {}; }
})();
const __F = CFG.fields || {};
const __pick = (...vals) => {
  for (const v of vals) {
    const s = String(v ?? '').trim();
    if (s && s.toLowerCase() !== 'null' && s.toLowerCase() !== 'undefined') return s;
  }
  return '';
};
const __name = __pick(n.lead.full_name, who);
const __co = __pick(n.lead.company, __pcf[__F.company_lh]);
const __web = __pick(n.lead.website);
const __li = __pick(n.lead.linkedin, __pcf[__F.linkedin_profile], __pcf[__F.linkedin_lh]);
// A missing field omits its LINE. "Company: None" reads as an answer; silence does not.
const __rows = [];
if (__name) __rows.push('Name: ' + esc(__name));
if (__co) __rows.push('Company: ' + esc(__co));
if (__web) __rows.push('Company website: ' + esc(__web));
if (__li) __rows.push('LinkedIn profile: ' + esc(__li));
const alert_text = __headline + (__rows.length ? '\\n*Details:*\\n' + __rows.join('\\n') : '');"""

# ---------------------------------------------------------------- WF-1
W1_OLD = ("const alert_text = '\\ud83d\\udcac ' + escapeSlack(aName) + aParen + aMetaStr "
          "+ ' \\u2014 ' + aLead + aLiLink;")
W1_NEW = """// Melisa's format: headline (built above) + a Details block. Same omit-the-line rule as WF-2.
const __L = (() => { try { return $('Normalize').item.json.lead || {}; } catch (e) { return {}; } })();
const __pick = (...vals) => {
  for (const v of vals) {
    const s = String(v ?? '').trim();
    if (s && s.toLowerCase() !== 'null' && s.toLowerCase() !== 'undefined') return s;
  }
  return '';
};
const __name = __pick(aName, __L.full_name);
const __co = __pick(aCo, __L.company_name);
const __web = __pick(__L.company_url);
const __li = __pick(aLi, __L.profile_url);
const __rows = [];
if (__name) __rows.push('Name: ' + escapeSlack(__name));
if (__co) __rows.push('Company: ' + escapeSlack(__co));
if (__web) __rows.push('Company website: ' + escapeSlack(__web));
if (__li) __rows.push('LinkedIn profile: ' + escapeSlack(__li));
const alert_text = __headline + (__rows.length ? '\\n*Details:*\\n' + __rows.join('\\n') : '');"""


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code}")


def run(js, label, harness, want):
    tmp = os.path.join(HERE, "_alert_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness.replace("__BODY__", js))
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-240:]}")
        return False, ""
    txt = json.loads(p.stdout.strip())["alert_text"]
    bad = []
    for must in want.get("has", []):
        if must not in txt:
            bad.append(f"missing {must!r}")
    for never in want.get("hasnt", []):
        if never in txt:
            bad.append(f"must NOT contain {never!r}")
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return (not bad), txt


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

w2 = n8n(f"/api/v1/workflows/{WF2}")
w1 = n8n(f"/api/v1/workflows/{WF1}")
W2O, W1O = copy.deepcopy(w2), copy.deepcopy(w1)
n2 = {n["name"]: n for n in w2["nodes"]}
n1 = {n["name"]: n for n in w1["nodes"]}
b2 = n2["Body Reply Alert"]["parameters"]["jsCode"]
b1 = n1["M7 Build"]["parameters"]["jsCode"]


def rewrite(src, details_js, drop_sllink):
    """Rename the existing `const alert_text = ...;` to __headline and append the Details block.

    Located STRUCTURALLY, not by matching its text: the live source contains literal emoji and
    typographic characters, and my first attempt anchored on \\uXXXX escapes that exist only in my
    Python string. Matching structure (assignment start -> statement-terminating semicolon) is
    immune to how those characters happen to be written.
    """
    key = "const alert_text = "
    i = src.find(key)
    if i < 0:
        raise SystemExit("no `const alert_text =` assignment found - refusing to patch blind")
    j = src.find(";\n", i)
    if j < 0:
        j = src.find(";", i)
    stmt = src[i:j + 1]
    head = stmt.replace(key, "const __headline = ", 1)
    if drop_sllink:
        head = head.replace(" + slLink", "")          # team alert drops the Smartlead link
        if "slLink" in head:
            raise SystemExit("slLink still present in the headline after removal")
    return src[:i] + head + "\n" + details_js + src[j + 1:]


new2 = b2 if "__headline" in b2 else rewrite(b2, W2_NEW, drop_sllink=True)
new1 = b1 if "__headline" in b1 else rewrite(b1, W1_NEW, drop_sllink=False)

CFGJS = ("{ fields: { company_lh: 'CO', linkedin_profile: 'LIP', linkedin_lh: 'LIL' },"
         " pipedrive_base: 'https://pd', sl_inbox_base: 'https://sl/' }")
H2 = """
const CFGV = %s;
const NORM = __NORM__;
const PCF  = __PCF__;
const $json = { __lead_id: 'L1', __person_id: 7 };
const $ = (nm) => {
  if (nm === 'CONFIG') return { item: { json: CFGV } };
  if (nm === 'Normalize') return { item: { json: NORM } };
  if (nm === 'R Person Verify') { if (PCF === null) throw new Error('nr'); return { item: { json: { data: { custom_fields: PCF } } } }; }
  throw new Error('absent ' + nm);
};
const __out = (() => {
__BODY__
})();
console.log(JSON.stringify({ alert_text: __out[0].json.alert_text }));
""" % CFGJS

FIXTURE = {"campaign_name": "[Events Visiting] AI4 2026 - Rune - Valids",
           "sender_inbox": "pii-95552f54@example.invalid", "sl_app_url": "https://app.smartlead.ai/x",
           "lead": {"email": "pii-c61c7d08@example.invalid", "full_name": "Кривошея",
                    "company": None, "website": None, "linkedin": None, "title": None}}
RICH = {"campaign_name": "C", "sender_inbox": "pii-c2b61be6@example.invalid", "sl_app_url": "https://app.smartlead.ai/y",
        "lead": {"email": "a@b.co", "full_name": "Ada L", "company": "Acme",
                 "website": "acme.com", "linkedin": "https://linkedin.com/in/pii-338ebd49", "title": "CTO"}}

print("--- statics: WF-2 team alert ---")
ok = True
_ok, t1 = run(new2, "fixture (company/website/LinkedIn all NULL) -> only Name, no empty lines",
              H2.replace("__NORM__", json.dumps(FIXTURE)).replace("__PCF__", "{}"),
              {"has": ["*Details:*", "Name: "],
               "hasnt": ["Open in Smartlead", "None", "undefined", "Company: \n",
                         "Company website:", "LinkedIn profile:"]})
ok = _ok and ok
_ok, t2 = run(new2, "rich payload -> all four rows, still no Smartlead link",
              H2.replace("__NORM__", json.dumps(RICH)).replace("__PCF__", "{}"),
              {"has": ["Name: Ada L", "Company: Acme", "Company website: acme.com",
                       "LinkedIn profile: https://linkedin.com/in/pii-338ebd49"],
               "hasnt": ["Open in Smartlead"]})
ok = _ok and ok
_ok, _ = run(new2, "person custom-field fallback supplies company + LinkedIn",
             H2.replace("__NORM__", json.dumps(FIXTURE)).replace(
                 "__PCF__", json.dumps({"CO": "Janea Systems", "LIP": "https://li/in/nik"})),
             {"has": ["Company: Janea Systems", "LinkedIn profile: https://li/in/nik"],
              "hasnt": ["Open in Smartlead"]})
ok = _ok and ok
_ok, _ = run(new2, "R Person Verify absent -> no throw, headline still built",
             H2.replace("__NORM__", json.dumps(FIXTURE)).replace("__PCF__", "null"),
             {"has": ["Name: "], "hasnt": ["Open in Smartlead", "None"]})
ok = _ok and ok
print(f"\n  sample: {t2[:200]!r}")

H1 = """
const NORM = __NORM__;
const $ = (nm) => { if (nm === 'Normalize') return { item: { json: NORM } };
                    throw new Error('absent ' + nm); };
const escapeSlack = (s) => String(s ?? '');
const aName = NORM.lead.full_name, aCo = NORM.lead.company_name, aLi = NORM.lead.profile_url;
const aParen = '', aMetaStr = '', aLead = '<pd|Open lead>';
const aLiLink = aLi ? ' \\u00b7 <' + aLi + '|LinkedIn>' : '';
__BODY__
console.log(JSON.stringify({ alert_text }));
"""
BOB = {"lead": {"full_name": "Person-0128acd7", "company_name": "Relational Intelligence Limited",
                "company_url": None,
                "profile_url": "https://www.linkedin.com/in/pii-d9f026c8"}}
BOB2 = {"lead": {"full_name": "Person-0128acd7", "company_name": "Relational Intelligence Limited",
                 "company_url": "relational.ai",
                 "profile_url": "https://www.linkedin.com/in/pii-d9f026c8"}}
print("\n--- statics: WF-1 team alert (real LinkedIn payload) ---")
w1body = ("const __headline = '\\ud83d\\udcac ' + escapeSlack(aName) + aParen + aMetaStr"
          " + ' \\u2014 ' + aLead + aLiLink;\n" + W1_NEW)
_ok, t3 = run(w1body, "Person-0128acd7, no company_url -> website line OMITTED",
              H1.replace("__NORM__", json.dumps(BOB)),
              {"has": ["Name: Person-0128acd7", "Company: Relational Intelligence Limited",
                       "LinkedIn profile: https://www.linkedin.com/in/pii-d9f026c8"],
               "hasnt": ["Company website:", "None", "undefined"]})
ok = _ok and ok
_ok, _ = run(w1body, "with company_url -> website line present",
             H1.replace("__NORM__", json.dumps(BOB2)),
             {"has": ["Company website: relational.ai"], "hasnt": ["None"]})
ok = _ok and ok
print(f"\n  sample: {t3[:220]!r}")
if not ok:
    sys.exit(1)

print("\n--- planned ---")
print(f"  WF-2 Body Reply Alert : Details block + Smartlead link removed "
      f"({'ADD' if '__headline' not in b2 else 'present'})")
print(f"  WF-1 M7 Build         : Details block ({'ADD' if '__headline' not in b1 else 'present'})")
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
for tag, orig in (("wf2", W2O), ("wf1", W1O)):
    with open(os.path.join(HERE, f"{tag}_backup_before_details_{stamp}.json"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(orig, indent=2, ensure_ascii=False))
n2["Body Reply Alert"]["parameters"]["jsCode"] = new2
n1["M7 Build"]["parameters"]["jsCode"] = new1
for wid, obj, tag in ((WF2, w2, "WF-2"), (WF1, w1, "WF-1")):
    d = stripped_keys(obj)
    if d:
        print(f"  {tag}: stripping {d}")
    n8n(f"/api/v1/workflows/{wid}", "PUT", put_body(obj))

a2 = n8n(f"/api/v1/workflows/{WF2}")
a1 = n8n(f"/api/v1/workflows/{WF1}")
x2 = {n["name"]: n for n in a2["nodes"]}["Body Reply Alert"]["parameters"]["jsCode"]
x1 = {n["name"]: n for n in a1["nodes"]}["M7 Build"]["parameters"]["jsCode"]
problems = []
if "__headline" not in x2 or "Details" not in x2:
    problems.append("WF-2 not patched")
if "slLink" in x2.split("const alert_text")[-1]:
    problems.append("WF-2 alert_text still uses slLink")
if "__headline" not in x1 or "Details" not in x1:
    problems.append("WF-1 not patched")
for w, o, t in ((a2, W2O, "WF-2"), (a1, W1O, "WF-1")):
    if w.get("active") is not o.get("active"):
        problems.append(f"{t} active={w.get('active')}")
    if len(w["nodes"]) != len(o["nodes"]):
        problems.append(f"{t} node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 {a2.get('versionId')} active={a2.get('active')} nodes={len(a2['nodes'])}")
print(f"  WF-1 {a1.get('versionId')} active={a1.get('active')} nodes={len(a1['nodes'])}")
sys.exit(1 if problems else 0)
