#!/usr/bin/env python3
"""LIVE LEAK — two defects in WF-2's SENT create path, fixed together. Finovate is sending NOW.

DEFECT A — ORPHANED LEADS (53 of 55 Finovate leads have person_id = null).
`Body Lead Create` reads `person_id: $json.__person_id`, but it is fed by
`Lead Select -> IF Lead Exists`, whose $json is the LEAD-LIST result. The person id is owned by
`Person Id Final` (verified: exec 35110 had __person_id 85825 there while Body Lead Create saw
null). This is B12 verbatim — "$json does NOT survive an HTTP node; recover context from the node
that OWNS it, by name" — the same trap the reply path was already hardened against. Fix uses the
identical waterfall.

DEFECT B — EMAIL AS THE PERSON NAME.
`Body Person Create` does `name: n.lead.full_name || n.lead.email`, and full_name is null because
`Apply Enrich` merges title/company/linkedin/website/location from the Smartlead lead but NEVER the
name. Smartlead had it all along - exec 35110's `SL Fetch Lead` returned first_name 'Lara',
last_name 'Lyberg'. This is the class we repaired 215 of on 18 Aug, recurring in a different
workflow. Rule then and now: **no name is derived from an email address**; provider truth or
nothing.

Person create sends the first/last PAIR when the provider has both - Pipedrive rejects `name`
together with the parts, and the parts are the structured truth (learned in the 215 repair). Email
remains the last-resort display value when the provider genuinely has no name, and is flagged.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
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
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

# ---------- A: Apply Enrich must carry the provider's NAME
ae = N["Apply Enrich"]["parameters"]["jsCode"]
if "merged.lead.first" in ae:
    sys.exit("Apply Enrich already carries names")
OLD_A = "merged.lead.company = merged.lead.company || d.company_name || null;"
if OLD_A not in ae:
    sys.exit("Apply Enrich company line not found verbatim")
NEW_A = """merged.lead.company = merged.lead.company || d.company_name || null;
// NAMES FROM PROVIDER TRUTH (2026-08-28). Enrichment merged company/title/linkedin but never the
// name, so `Body Person Create` fell through to `n.lead.email` and created persons literally named
// pii-c7524b7a@example.invalid while Smartlead held 'Lara' / 'Lyberg'. Same class as the 215 sprint
// names repaired 18 Aug. No name is ever derived from an email address - provider truth or nothing.
merged.lead.first = merged.lead.first || d.first_name || null;
merged.lead.last = merged.lead.last || d.last_name || null;
merged.lead.full_name = merged.lead.full_name
  || [merged.lead.first, merged.lead.last].filter(Boolean).join(' ')
  || null;"""
N["Apply Enrich"]["parameters"]["jsCode"] = ae.replace(OLD_A, NEW_A, 1)

# ---------- B: Body Person Create sends the structured pair
bpc = N["Body Person Create"]["parameters"]["jsCode"]
OLD_B = "const body = { name: n.lead.full_name || n.lead.email, owner_id: CFG.owner_id, custom_fields: cf };"
if OLD_B not in bpc:
    sys.exit("Body Person Create body line not found verbatim")
NEW_B = """// Pipedrive rejects `name` together with first_name/last_name - send the PAIR when the provider
// gave both (structured truth, and it populates the parts rather than only a display string).
// Email is the LAST resort and is flagged, never a derived name.
const __first = (n.lead.first || '').trim();
const __last = (n.lead.last || '').trim();
const __full = (n.lead.full_name || '').trim();
const __name_from_provider = !!(__first || __last || __full);
const body = (__first && __last)
  ? { first_name: __first, last_name: __last, owner_id: CFG.owner_id, custom_fields: cf }
  : { name: __full || n.lead.email, owner_id: CFG.owner_id, custom_fields: cf };"""
bpc = bpc.replace(OLD_B, NEW_B, 1)
bpc = bpc.replace("return [{ json: { __body: body, __intended:",
                  "return [{ json: { __body: body, __name_from_provider,\n  __intended:", 1)
N["Body Person Create"]["parameters"]["jsCode"] = bpc

# ---------- C: Body Lead Create must read the person id from the node that OWNS it
blc = N["Body Lead Create"]["parameters"]["jsCode"]
OLD_C = "  person_id: $json.__person_id ?? null,"
if OLD_C not in blc:
    sys.exit("Body Lead Create person_id line not found verbatim")
NEW_C = """  // B12: $json here is the LEAD-LIST result (fed via Lead Select -> IF Lead Exists), so
  // $json.__person_id was always null and every created lead was ORPHANED - 53 of 55 on Finovate.
  // Recover from the node that OWNS the id, by name, exactly as the reply path already does.
  person_id: (() => {
    if ($json && $json.__person_id) return $json.__person_id;
    for (const nm of ['Person Id Final', 'Carry Person Ctx', 'Person Pick']) {
      try { const v = $(nm).item.json.__person_id; if (v) return v; } catch (e) {}
    }
    return null;
  })(),"""
blc = blc.replace(OLD_C, NEW_C, 1)
OLD_D = "const orgId = $json.__org_id ?? null;"
if OLD_D in blc:
    blc = blc.replace(OLD_D, """const orgId = (() => {
  if ($json && $json.__org_id) return $json.__org_id;
  for (const nm of ['Person Id Final', 'Carry Person Ctx']) {
    try { const v = $(nm).item.json.__org_id; if (v) return v; } catch (e) {}
  }
  return null;
})();""", 1)
N["Body Lead Create"]["parameters"]["jsCode"] = blc

# ---------------------------------------------------------------- statics
print("--- statics ---")
ok = True
HERE_ = HERE


def run(js, harness, pick):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(" + pick + "));\n"
    tmp = os.path.join(HERE_, "_fl.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:280]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


SLLEAD = {"first_name": "Lara", "last_name": "Lyberg", "company_name": "Citizens Bank",
          "email": "pii-c7524b7a@example.invalid", "website": "citizensbank.com",
          "custom_fields": {"Title": "SVP"}}
NORM = {"campaign_id": 3868450, "campaign_name": "[Events Visiting] [FinovateFall 2026] - Noah - Catch-alls",
        "lead": {"email": "pii-c7524b7a@example.invalid", "first": None, "last": None,
                 "full_name": None, "company": None, "title": None, "linkedin": None,
                 "website": None, "location": None}}

# 1. Apply Enrich now carries the name
h = f"""
const NORM = {json.dumps(NORM)};
const $json = {json.dumps(SLLEAD)};
const $ = (nm) => {{ if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
                     throw new Error('absent ' + nm); }};
"""
got, err = run(N["Apply Enrich"]["parameters"]["jsCode"], h,
               "{f: OUT[0].json.__enriched.lead.first, l: OUT[0].json.__enriched.lead.last,"
               " fn: OUT[0].json.__enriched.lead.full_name}")
if err:
    print(f"  [FAIL] Apply Enrich: {err}")
    ok = False
else:
    good = got["f"] == "Lara" and got["l"] == "Lyberg" and got["fn"] == "Person-8bb29b7c"
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] Apply Enrich carries provider name -> {got}")

# 2/3. Body Person Create with and without a provider name
CFGJ = {"owner_id": 16340280, "medium_value": "eMail", "source_value": 446,
        "fields": {"company_lh": "C", "campaign": "K", "event_name": "E", "medium": "M",
                   "source": "S", "title_std_cf": "T", "position_lh": "P",
                   "linkedin_lh": "L", "org_website_lh": "W", "location_lh": "O",
                   "hypothesis": "H", "title_linkedin": "TL", "linkedin_profile": "LP"}}
for label, lead, want_parts in (
        ("provider HAS the name -> first/last pair, no `name` key",
         dict(NORM["lead"], first="Lara", last="Lyberg", full_name="Person-8bb29b7c"), True),
        ("provider has NO name -> falls back to email, flagged",
         dict(NORM["lead"]), False)):
    nrm = dict(NORM, lead=lead)
    h2 = f"""
const CFG = {json.dumps(CFGJ)};
const NORM = {json.dumps(nrm)};
const $json = {{ __org_id: 3207 }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Apply Enrich') return {{ item: {{ json: {{ __enriched: NORM }} }} }};
  throw new Error('absent ' + nm);
}};
"""
    got, err = run(N["Body Person Create"]["parameters"]["jsCode"], h2,
                   "{b: OUT[0].json.__body, prov: OUT[0].json.__name_from_provider}")
    if err:
        print(f"  [FAIL] {label}: {err}")
        ok = False
        continue
    b = got["b"]
    if want_parts:
        good = (b.get("first_name") == "Lara" and b.get("last_name") == "Lyberg"
                and "name" not in b and got["prov"] is True)
    else:
        good = (b.get("name") == "pii-c7524b7a@example.invalid"
                and "first_name" not in b and got["prov"] is False)
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         body keys={sorted(b.keys())} name={b.get('name')!r} "
          f"first={b.get('first_name')!r} provider={got['prov']}")

# 4. Body Lead Create picks the pid up from Person Id Final
# built outside the f-string: `{{...}}` inside an f-string EXPRESSION is a set literal, not a dict
CFG3 = dict(CFGJ, lead_channel=578, lead_opportunity_type_value=480,
            labels={"cold": "C"},
            fields=dict(CFGJ["fields"], lead_campaign="LC", lead_opportunity_type="LO"))
h3 = f"""
const CFG = {json.dumps(CFG3)};
const NORM = {json.dumps(dict(NORM, lead=dict(NORM["lead"], first="Lara", last="Lyberg", full_name="Person-8bb29b7c")))};
const $json = {{ success: true, data: [] }};   // the LEAD-LIST result, as in production
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Apply Enrich') return {{ item: {{ json: {{ __enriched: NORM }} }} }};
  if (nm === 'Person Id Final') return {{ item: {{ json: {{ __person_id: 85825, __org_id: 3207 }} }} }};
  if (nm === 'Merge Reply Ctx') throw new Error('not on this path');
  throw new Error('absent ' + nm);
}};
"""
got, err = run(N["Body Lead Create"]["parameters"]["jsCode"], h3, "OUT[0].json.__body")
if err:
    print(f"  [FAIL] Body Lead Create: {err}")
    ok = False
else:
    good = got.get("person_id") == 85825 and got.get("organization_id") == 3207
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] Body Lead Create recovers the pid by node name")
    print(f"         person_id={got.get('person_id')} org={got.get('organization_id')} "
          f"title={str(got.get('title'))[:56]!r}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_finovate_leak_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "merged.lead.first" not in AN["Apply Enrich"]["parameters"]["jsCode"]:
    problems.append("Apply Enrich name merge not live")
if "__name_from_provider" not in AN["Body Person Create"]["parameters"]["jsCode"]:
    problems.append("Body Person Create pair not live")
if "Person Id Final" not in AN["Body Lead Create"]["parameters"]["jsCode"]:
    problems.append("Body Lead Create pid waterfall not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
