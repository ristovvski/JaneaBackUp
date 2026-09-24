#!/usr/bin/env python3
"""CONSOLIDATED AMENDMENT — WF-2: a campaign reply with no lead now CREATES, then classifies.

Ruling (Nik): a reply from OUR campaign = create the lead automatically, always. Campaign membership
IS the qualification. A reply outside campaigns = personal conversation: no creation, no alert.

BRANCH ORDER (amendment A):
  1) campaign-attributed reply + no lead  -> CREATE (person if missing + lead), then
  2) classify: OOO/auto -> silent (no alert, no Responded, lead stays '1. Cold')
                real     -> alert WITH the lead link + Responded, as today
OOO suppresses the ALERT and the LABEL - never the creation. That is the Lara fix: her lead should
exist, her auto-reply should say nothing.

WHY NEW NODES: the reply path cannot reach a single SENT-path creator (verified by graph walk -
Body Person Create / Person Create / Body Lead Create / Lead Create are all unreachable from
Merge Reply Ctx). Reusing them would mean fanning the reply into the SENT continuation
(Lead Create -> Claim SENT), which would claim a SENT that never happened.

NOT IN THIS CHANGE - the categorisation race (amendment item 4). Smartlead delivers a reply BEFORE
it has categorised it and re-delivers with the category (Lara: uncategorised 11:04, 'Out Of Office'
11:15), so the first pass still announces. Closing it needs a fresh category read plus a change to
First Reply Gate's OOO source - a separable change, deliberately NOT bundled into a seven-node
structural edit of a live workflow on the same day three defects were found here. Effect until then:
one false alert per OOO reply, and the lead now exists either way.

Nodes added (7):
  R Create Gate        IF   campaign-attributed AND no lead
  R Body Person Create code build person body from provider truth (never email-derived names)
  R Person Create      http onError continue
  R Body Lead Create   code campaign-titled lead, open-deal guard honoured
  R Lead Create        http onError continue
  R Lead Ctx           code merge new ids back into the reply context; flag failure
  R IF Create Failed   IF   -> the existing Ops Warn No Lead (now only fires on real failure)
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
PDCRED = {"pipedriveApi": {"id": "HnyULgvDdYp0lIkB", "name": "Pipedrive account"}}

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
C = wf.setdefault("connections", {})
if "R Create Gate" in N:
    sys.exit("reply-create branch already present")

BX, BY = N["IF No Lead"]["position"]

CREATE_GATE = ("={{ (() => { const j = $json || {};"
               " const n = (() => { try { return $('Normalize').item.json || {}; }"
               "   catch (e) { return {}; } })();"
               " const camp = n.campaign_id ?? n.campaign?.id ?? n.campaign_name ?? null;"
               " return j.__no_lead === true && !!camp; })() }}")

R_BODY_PERSON = r"""
// Build the person body for a CAMPAIGN reply that has no lead yet.
// Provider truth only: names come from Normalize/enrichment, NEVER derived from the address
// (the 215-name repair rule, and the reason WF-2's SENT path was fixed on 2026-08-28).
const CFG = $('CONFIG').item.json;
const F = CFG.fields || {};
const n = $('Normalize').item.json;
const ctxj = $json || {};
const L = n.lead || {};
const omit = (o) => { for (const k of Object.keys(o)) {
  const v = o[k]; if (v === '' || v === null || v === undefined) delete o[k]; } return o; };

const cf = {};
if (L.company) cf[F.company_lh] = L.company;
if (L.title) cf[F.title_std_cf] = L.title;
if (L.linkedin) cf[F.linkedin_lh] = L.linkedin;
if (L.location) cf[F.location_lh] = L.location;
if (n.campaign_name) cf[F.campaign] = n.campaign_name;
if (n.hypothesis) cf[F.hypothesis] = n.hypothesis;
if (n.event_name) cf[F.event_name] = n.event_name;
cf[F.medium] = CFG.medium_value;
cf[F.source] = CFG.source_value;
omit(cf);

const first = String(L.first || '').trim();
const last = String(L.last || '').trim();
const full = String(L.full_name || '').trim();
const __name_from_provider = !!(first || last || full);
const body = (first && last)
  ? { first_name: first, last_name: last, owner_id: CFG.owner_id, custom_fields: cf }
  : { name: full || L.email, owner_id: CFG.owner_id, custom_fields: cf };
if (L.email) body.emails = [{ value: L.email, primary: true, label: 'work' }];

// person may already exist - only create when the resolver found nothing
const __skip = !!ctxj.__person_id;
return [{ json: { ...ctxj, __body: body, __skip, __name_from_provider,
  __intended: { node: 'R Person Create', method: 'POST', url: '/api/v2/persons', body } } }];
"""

R_BODY_LEAD = r"""
// Campaign-titled lead for a reply that arrived before any lead existed.
// Honours the open-deal guard: a person already represented by an OPEN DEAL never gets a new lead.
const CFG = $('CONFIG').item.json;
const F = CFG.fields || {};
const n = $('Normalize').item.json;
const ctxj = (() => { try { return $('R Body Person Create').item.json || {}; }
                      catch (e) { return $json || {}; } })();
const omit = (o) => { for (const k of Object.keys(o)) {
  const v = o[k]; if (v === '' || v === null || v === undefined) delete o[k]; } return o; };

// person id: the one we just created, else the one the resolver already had
const pid = (() => {
  try { const c = $('R Person Create').item.json; const id = c?.data?.id ?? c?.id;
        if (id) return id; } catch (e) {}
  return ctxj.__person_id ?? null;
})();

const hasDeal = !!ctxj.__deal_id;
const dealUnknown = ctxj.__deal_check_failed === true;
const __block = hasDeal || dealUnknown || !pid;

const title = [n.campaign_id, n.campaign_name, (n.lead || {}).full_name]
  .filter(v => v !== null && v !== undefined && v !== '').map(String).join(' - ');
const body = { title, person_id: pid, owner_id: CFG.owner_id,
               label_ids: [CFG.labels.cold], channel: CFG.lead_channel };
body[F.lead_campaign] = n.campaign_name;
body[F.lead_opportunity_type] = CFG.lead_opportunity_type_value;
if (ctxj.__org_id) body.organization_id = ctxj.__org_id;
omit(body);
return [{ json: { ...ctxj, __person_id: pid, __body: body, __skip: __block,
  __block_reason: hasDeal ? ('open_deal:' + ctxj.__deal_id)
    : (dealUnknown ? 'deal_check_failed' : (!pid ? 'no_person' : null)),
  __intended: { node: 'R Lead Create', method: 'POST', url: '/v1/leads', body } } }];
"""

R_LEAD_CTX = r"""
// Merge the newly created ids back into the reply context so everything downstream - the alert, the
// label union, the reply activity - behaves exactly as it would for a pre-existing lead.
const prev = (() => { try { return $('R Body Lead Create').item.json || {}; }
                      catch (e) { return {}; } })();
const created = (() => { try { const r = $('R Lead Create').item.json;
  return r?.data?.id ?? r?.id ?? null; } catch (e) { return null; } })();
const leadId = created ?? prev.__lead_id ?? null;
const blocked = prev.__skip === true;
return [{ json: { ...prev, __lead_id: leadId, __no_lead: !leadId,
  __lead_created: !!created,
  // a genuine failure is: we intended to create and got nothing back. Blocked-by-guard is not a
  // failure - an open-deal person is correctly left without a lead.
  __create_failed: (!blocked && !created),
  __create_block_reason: prev.__block_reason ?? null } }];
"""

nodes_new = [
    {"name": "R Create Gate", "type": "n8n-nodes-base.if", "typeVersion": 2,
     "position": [BX + 180, BY + 240], "id": "rc-gate-0001",
     "parameters": {"conditions": {
         "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
         "combinator": "and",
         "conditions": [{"id": "rc-c1", "leftValue": CREATE_GATE, "rightValue": True,
                         "operator": {"type": "boolean", "operation": "true",
                                      "singleValue": True}}]}, "options": {}}},
    {"name": "R Body Person Create", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [BX + 360, BY + 240], "id": "rc-bpc-0001",
     "parameters": {"jsCode": R_BODY_PERSON}},
    {"name": "R Person Create", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [BX + 540, BY + 240], "id": "rc-pc-0001", "credentials": PDCRED,
     "onError": "continueRegularOutput",
     "parameters": {"method": "POST",
                    "url": "={{ $('CONFIG').item.json.pd_api }}{{ '/api/v2/persons' }}",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "pipedriveApi",
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.__body) }}",
                    "sendHeaders": True,
                    "headerParameters": {"parameters": [
                        {"name": "Content-Type", "value": "application/json"}]},
                    "options": {}}},
    {"name": "R Body Lead Create", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [BX + 720, BY + 240], "id": "rc-blc-0001",
     "parameters": {"jsCode": R_BODY_LEAD}},
    {"name": "R Lead Create", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [BX + 900, BY + 240], "id": "rc-lc-0001", "credentials": PDCRED,
     "onError": "continueRegularOutput",
     "parameters": {"method": "POST",
                    "url": "={{ $('CONFIG').item.json.pd_api }}{{ '/v1/leads' }}",
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "pipedriveApi",
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.__body) }}",
                    "sendHeaders": True,
                    "headerParameters": {"parameters": [
                        {"name": "Content-Type", "value": "application/json"}]},
                    "options": {}}},
    {"name": "R Lead Ctx", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [BX + 1080, BY + 240], "id": "rc-ctx-0001",
     "parameters": {"jsCode": R_LEAD_CTX}},
    {"name": "R IF Create Failed", "type": "n8n-nodes-base.if", "typeVersion": 2,
     "position": [BX + 1260, BY + 420], "id": "rc-iff-0001",
     "parameters": {"conditions": {
         "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
         "combinator": "and",
         "conditions": [{"id": "rc-c2", "leftValue": "={{ $json.__create_failed === true }}",
                         "rightValue": True,
                         "operator": {"type": "boolean", "operation": "true",
                                      "singleValue": True}}]}, "options": {}}},
]
wf["nodes"].extend(nodes_new)
N.update({x["name"]: x for x in nodes_new})

# ---- rewire: IF No Lead out0 now goes to the create gate, not straight to the alert gate
C["IF No Lead"] = {"main": [
    [{"node": "R Create Gate", "type": "main", "index": 0}],
    [{"node": "First Reply Gate", "type": "main", "index": 0}]]}
C["R Create Gate"] = {"main": [
    [{"node": "R Body Person Create", "type": "main", "index": 0}],
    [{"node": "First Reply Gate", "type": "main", "index": 0}]]}
C["R Body Person Create"] = {"main": [[{"node": "R Person Create", "type": "main", "index": 0}]]}
C["R Person Create"] = {"main": [[{"node": "R Body Lead Create", "type": "main", "index": 0}]]}
C["R Body Lead Create"] = {"main": [[{"node": "R Lead Create", "type": "main", "index": 0}]]}
C["R Lead Create"] = {"main": [[{"node": "R Lead Ctx", "type": "main", "index": 0}]]}
C["R Lead Ctx"] = {"main": [[{"node": "First Reply Gate", "type": "main", "index": 0},
                             {"node": "R IF Create Failed", "type": "main", "index": 0}]]}
C["R IF Create Failed"] = {"main": [
    [{"node": "Ops Warn No Lead", "type": "main", "index": 0}], []]}

# ---- retire the "not in CRM yet" notice
bra = N["Body Reply Alert"]["parameters"]["jsCode"]
OLDN = "'no lead · not in CRM yet'"
if OLDN in bra:
    bra = bra.replace(OLDN, "'lead pending'", 1)
    N["Body Reply Alert"]["parameters"]["jsCode"] = bra
    print("retired the 'not in CRM yet' notice text")

print(f"added {len(nodes_new)} nodes; rewired IF No Lead -> R Create Gate")

# ---------------------------------------------------------------- statics
print("\n--- statics ---")
ok = True


def run(js, harness, pick):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(" + pick + "));\n"
    tmp = os.path.join(HERE, "_rc.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


CFGJ = {"pd_api": "https://api.pipedrive.com", "owner_id": 16340280, "lead_channel": 578,
        "lead_opportunity_type_value": 480, "medium_value": "eMail", "source_value": 446,
        "labels": {"cold": "COLD"},
        "fields": {"company_lh": "C", "title_std_cf": "T", "linkedin_lh": "L", "location_lh": "O",
                   "campaign": "K", "hypothesis": "H", "event_name": "E", "medium": "M",
                   "source": "S", "lead_campaign": "LC", "lead_opportunity_type": "LO"}}
NORM = {"campaign_id": 3868449, "campaign_name": "[Events Visiting] [FinovateFall 2026] - Noah - Valids",
        "lead": {"email": "pii-febd7426@example.invalid", "first": "Kyle", "last": "Strougo",
                 "full_name": "Person-a9a7d542", "company": "BNP Paribas", "title": None,
                 "linkedin": None, "location": None}}


def h(ctxj, norm=None, personresp=None, leadresp=None, prev=None):
    return f"""
const CFG = {json.dumps(CFGJ)};
const NORM = {json.dumps(norm or NORM)};
const $json = {json.dumps(ctxj)};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'R Body Person Create') return {{ item: {{ json: {json.dumps(ctxj)} }} }};
  if (nm === 'R Person Create') {{ {'return { item: { json: ' + json.dumps(personresp) + ' } };' if personresp is not None else "throw new Error('did not run');"} }}
  if (nm === 'R Body Lead Create') return {{ item: {{ json: {json.dumps(prev or {})} }} }};
  if (nm === 'R Lead Create') {{ {'return { item: { json: ' + json.dumps(leadresp) + ' } };' if leadresp is not None else "throw new Error('did not run');"} }}
  throw new Error('absent ' + nm);
}};
"""


CTX_NEW = {"__no_lead": True, "__person_id": None, "__deal_id": None,
           "__deal_check_failed": False, "__org_id": None}
CTX_KNOWN = dict(CTX_NEW, __person_id=90001)
CTX_DEAL = dict(CTX_NEW, __person_id=69696, __deal_id=2093)

# 1. person body from provider truth
got, err = run(N["R Body Person Create"]["parameters"]["jsCode"], h(CTX_NEW),
               "{b: OUT[0].json.__body, skip: OUT[0].json.__skip, prov: OUT[0].json.__name_from_provider}")
good = (not err and got["b"].get("first_name") == "Kyle" and "name" not in got["b"]
        and got["skip"] is False and got["prov"] is True)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] campaign reply, no person -> creates with PROVIDER name"
      f"  {err or ''}")
if not err:
    print(f"         body={sorted(got['b'].keys())} first={got['b'].get('first_name')!r}")

# 2. person already known -> skip person create
got, err = run(N["R Body Person Create"]["parameters"]["jsCode"], h(CTX_KNOWN),
               "{skip: OUT[0].json.__skip}")
good = (not err and got["skip"] is True)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] person already known -> person create SKIPPED")

# 3. lead body, person just created
got, err = run(N["R Body Lead Create"]["parameters"]["jsCode"],
               h(CTX_NEW, personresp={"data": {"id": 90123}}),
               "{b: OUT[0].json.__body, skip: OUT[0].json.__skip, r: OUT[0].json.__block_reason}")
good = (not err and got["skip"] is False and got["b"].get("person_id") == 90123
        and str(got["b"].get("title")).startswith("3868449 - "))
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] lead built, linked to the new person  {err or ''}")
if not err:
    print(f"         person_id={got['b'].get('person_id')} title={str(got['b'].get('title'))[:56]!r}")

# 4. ANDREA GUARD: open deal -> no lead
got, err = run(N["R Body Lead Create"]["parameters"]["jsCode"],
               h(CTX_DEAL, personresp={"data": {"id": 69696}}),
               "{skip: OUT[0].json.__skip, r: OUT[0].json.__block_reason}")
good = (not err and got["skip"] is True and str(got["r"]).startswith("open_deal:"))
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] replier with an OPEN DEAL -> no lead created "
      f"({got['r'] if not err else err})")

# 5. ctx merge: created
got, err = run(N["R Lead Ctx"]["parameters"]["jsCode"],
               h(CTX_NEW, leadresp={"data": {"id": "LEAD-1"}},
                 prev=dict(CTX_NEW, __skip=False, __person_id=90123)),
               "{lead: OUT[0].json.__lead_id, nolead: OUT[0].json.__no_lead,"
               " failed: OUT[0].json.__create_failed}")
good = (not err and got["lead"] == "LEAD-1" and got["nolead"] is False
        and got["failed"] is False)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] created -> __lead_id set, __no_lead false, not failed")

# 6. ctx merge: blocked by guard is NOT a failure
got, err = run(N["R Lead Ctx"]["parameters"]["jsCode"],
               h(CTX_DEAL, prev=dict(CTX_DEAL, __skip=True, __block_reason="open_deal:2093")),
               "{failed: OUT[0].json.__create_failed, r: OUT[0].json.__create_block_reason}")
good = (not err and got["failed"] is False and got["r"] == "open_deal:2093")
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] blocked by the deal guard -> NOT reported as a failure")

# 7. ctx merge: genuine failure
got, err = run(N["R Lead Ctx"]["parameters"]["jsCode"],
               h(CTX_NEW, prev=dict(CTX_NEW, __skip=False)),
               "{failed: OUT[0].json.__create_failed}")
good = (not err and got["failed"] is True)
ok = good and ok
print(f"  [{'ok ' if good else 'FAIL'}] intended to create but got nothing -> __create_failed")

# 8. the gate expression
for label, ctxj, norm, want in (
        ("campaign reply + no lead -> ENTER create branch", CTX_NEW, NORM, True),
        ("manual chat (no campaign) -> SKIP create branch", CTX_NEW,
         dict(NORM, campaign_id=None, campaign_name=None), False),
        ("campaign reply that already has a lead -> SKIP",
         dict(CTX_NEW, __no_lead=False), NORM, False)):
    body = CREATE_GATE.strip()[4:-3].strip()
    src = h(ctxj, norm) + f"console.log(JSON.stringify({{v: ({body})}}));"
    tmp = os.path.join(HERE, "_rcg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[:180]}")
        ok = False
        continue
    v = json.loads(p.stdout.strip().splitlines()[-1])["v"]
    good = v is want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}  -> {v}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_replycreate_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
for nm in [x["name"] for x in nodes_new]:
    if nm not in AN:
        problems.append(f"{nm} missing")
for nm in ("R Person Create", "R Lead Create"):
    if AN.get(nm, {}).get("onError") != "continueRegularOutput":
        problems.append(f"{nm} is BLOCKING")
outs = [c.get("node") for g in (AC.get("IF No Lead") or {}).get("main", []) for c in (g or [])]
if "R Create Gate" not in outs:
    problems.append(f"IF No Lead not rewired: {outs}")
if len(after["nodes"]) != len(ORIG["nodes"]) + len(nodes_new):
    problems.append("node count wrong")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
