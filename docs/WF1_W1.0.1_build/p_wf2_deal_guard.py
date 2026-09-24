#!/usr/bin/env python3
"""1(b) CLASS FIX, WF-2 — a person with 0 leads may still be fully represented by an OPEN DEAL.

Person-7267ff83: person 69696, 0 leads, open deal since April with 8 activities. My repair read the
truthful `0 leads` as `not represented` and created a duplicate, which spawned a Handover task into
Melisa's reports. A person converted to a deal ALWAYS has zero leads — the emptiest possible answer
came from the most advanced possible state.

CHANGES
  + R Deal List        GET /api/v2/deals?person_id&status=open, inserted Lead Resolve -> Merge
  ~ Merge Reply Ctx    reads Lead Resolve BY NAME (it used $json, which the insert would shift);
                       emits __deal_id / __deal_title / __deal_check_failed
  ~ Body Lead Create   refuses to create when an open deal exists OR the deal check FAILED
  ~ Body Reply Activity targets the DEAL when there is a deal and no lead

FAIL DIRECTION (9b.0f): the lookup is continueRegularOutput so a Pipedrive hiccup cannot break reply
processing — but an UNKNOWN deal state makes lead creation fail CLOSED. Creating a duplicate is what
reaches Melisa's queue; not creating is recoverable. Failing open would reinstate the bug.
"""
import argparse, copy, json, os, re, ssl, subprocess, sys, urllib.request
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
C = wf.setdefault("connections", {})
if "R Deal List" in N:
    sys.exit("R Deal List already present - nothing to do")

PID = ("={{ (() => { let p = null;"
       " try { const v = $('R Person Verify Apply').item.json; if (v && v.__person_id) p = v.__person_id; } catch (e) {}"
       " if (!p) { try { p = $('R Person Pick').item.json.__person_id; } catch (e) {} }"
       " return p || 0; })() }}")
lx, ly = N["Lead Resolve"]["position"]
wf["nodes"].append({
    "parameters": {"method": "GET",
                   "url": "={{ $('CONFIG').item.json.pd_api }}{{ '/api/v2/deals' }}",
                   "sendQuery": True,
                   "queryParameters": {"parameters": [
                       {"name": "person_id", "value": PID},
                       {"name": "status", "value": "open"},
                       {"name": "limit", "value": "50"}]},
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [
                       {"name": "Content-Type", "value": "application/json"}]},
                   "options": {}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "position": [lx + 200, ly + 200], "id": "dealguard-list-0001", "name": "R Deal List",
    "credentials": N["R Lead List"].get("credentials"),
    "onError": "continueRegularOutput"})
C["Lead Resolve"] = {"main": [[{"node": "R Deal List", "type": "main", "index": 0}]]}
C["R Deal List"] = {"main": [[{"node": "Merge Reply Ctx", "type": "main", "index": 0}]]}

# ---- Merge Reply Ctx
m = N["Merge Reply Ctx"]["parameters"]["jsCode"]
OLD = "const lr = $json;"
if OLD not in m:
    sys.exit("Merge Reply Ctx first line not found verbatim")
NEW = """// R Deal List now sits between Lead Resolve and this node, so $json is the DEALS response. Read
// the lead result BY NAME rather than positionally - the point of the insert is that this node goes
// on meaning the same thing.
const lr = $('Lead Resolve').item.json;
// OPEN DEALS for this person. A person converted to a deal has ZERO leads, so "0 leads" alone is
// not evidence of absence (Person-7267ff83, 2026-08-14). __deal_check_failed is NOT "no deal":
// unknown must never read as absent.
const __deals = (() => {
  try {
    const r = $json;
    if (!r || r.success === false) return { failed: true, list: [] };
    const d = Array.isArray(r.data) ? r.data : (Array.isArray(r) ? r : null);
    if (d === null) return { failed: true, list: [] };
    return { failed: false, list: d.filter(x => String((x || {}).status || '') === 'open') };
  } catch (e) { return { failed: true, list: [] }; }
})();
const __deal = __deals.list[0] || null;"""
m = m.replace(OLD, NEW, 1)
mm = re.search(r"return \[\{\s*json:\s*\{", m)
if not mm:
    sys.exit("Merge Reply Ctx return shape not recognised")
m = m[:mm.end()] + ("\n  __deal_id: __deal ? __deal.id : null,"
                    "\n  __deal_title: __deal ? __deal.title : null,"
                    "\n  __deal_check_failed: __deals.failed,") + m[mm.end():]
N["Merge Reply Ctx"]["parameters"]["jsCode"] = m

# ---- Body Lead Create
blc = N["Body Lead Create"]["parameters"]["jsCode"]
ANCH = "const title = ["
if ANCH not in blc:
    sys.exit("Body Lead Create anchor missing")
GUARD = """// DEAL GUARD (2026-08-18). Never create a lead for a person who is already an open DEAL - that is
// the same human duplicated at an earlier pipeline stage, and it spawns a Handover into Melisa's
// queue. Fails CLOSED on an unknown deal state: creating is the act that reaches people, so
// uncertainty must not create (9b.0f - write gates fail closed).
const __dealCtx = (() => {
  try { return $('Merge Reply Ctx').item.json || {}; } catch (e) { return {}; }
})();
const __hasDeal = !!__dealCtx.__deal_id;
const __dealUnknown = __dealCtx.__deal_check_failed === true;
const __blockCreate = __hasDeal || __dealUnknown;
"""
blc = blc.replace(ANCH, GUARD + ANCH, 1)
OLDR = "return [{ json: { __body: body, __intended:"
if OLDR not in blc:
    sys.exit("Body Lead Create return not found verbatim")
blc = blc.replace(OLDR,
                  "return [{ json: { __body: body, __skip: __blockCreate,\n"
                  "  __block_reason: __hasDeal ? ('open_deal:' + __dealCtx.__deal_id)\n"
                  "    : (__dealUnknown ? 'deal_check_failed' : null),\n  __intended:", 1)
N["Body Lead Create"]["parameters"]["jsCode"] = blc

# ---- Body Reply Activity
bra = N["Body Reply Activity"]["parameters"]["jsCode"]
OLDB = ("const body = { subject: 'Email reply — ' + n.campaign_name, type: 'email', done: true,\n"
        "               owner_id: CFG.owner_id, lead_id: ctx('__lead_id', 'Merge Reply Ctx', "
        "'Lead Resolve') };")
if OLDB not in bra:
    sys.exit("Body Reply Activity body block not found verbatim")
NEWB = """// Target the DEAL when the person is represented by one and has no lead. Same reply, correct home
// - this is what should have happened for Andrea instead of creating a duplicate lead for it to
// hang on. person_id is READ-ONLY on /api/v2/activities; it must go through participants.
const __lid = ctx('__lead_id', 'Merge Reply Ctx', 'Lead Resolve');
const __did = ctx('__deal_id', 'Merge Reply Ctx');
const __pid = ctx('__person_id', 'Merge Reply Ctx', 'R Person Pick');
const body = { subject: 'Email reply — ' + n.campaign_name, type: 'email', done: true,
               owner_id: CFG.owner_id };
if (__lid) { body.lead_id = __lid; }
else if (__did) { body.deal_id = __did;
  if (__pid) body.participants = [{ person_id: __pid, primary: true }]; }"""
bra = bra.replace(OLDB, NEWB, 1)
OLDS = "__skip: !ctx('__lead_id', 'Merge Reply Ctx', 'Lead Resolve'),"
if OLDS not in bra:
    sys.exit("Body Reply Activity skip line not found verbatim")
bra = bra.replace(OLDS, "__skip: !(__lid || __did),\n  __activity_target: __lid ? 'lead' "
                        ": (__did ? 'deal' : null),", 1)
N["Body Reply Activity"]["parameters"]["jsCode"] = bra

# ---------------------------------------------------------------- statics
print("--- statics: THE ANDREA SHAPE ---")
ok = True


def run(js, harness):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(OUT[0].json));\n"
    tmp = os.path.join(HERE, "_dg.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


CFGJ = ("{ pd_api: 'https://api.pipedrive.com', owner_id: 16340280, lead_channel: 578,"
        " lead_opportunity_type_value: 480, labels: { cold: 'C' },"
        " fields: { lead_campaign: 'F_CAMP', lead_opportunity_type: 'F_OPP' } }")
NORMJ = ("{ campaign_id: 3085711, campaign_name: 'HumanX', reply: { subject: 's', body: 'b',"
         " received_at: '2026-08-13T16:37:19Z' },"
         " lead: { email: 'pii-362de426@example.invalid', full_name: 'Person-7267ff83' } }")


def harness(deal_id, failed, lead_id, person_id=69696):
    merge = {"__deal_id": deal_id, "__deal_check_failed": failed,
             "__lead_id": lead_id, "__person_id": person_id}
    return f"""
const CFG = {CFGJ};
const NORM = {NORMJ};
const MERGE = {json.dumps(merge)};
const $json = MERGE;
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'Merge Reply Ctx') return {{ item: {{ json: MERGE }} }};
  if (nm === 'Lead Resolve') return {{ item: {{ json: {{ __lead_id: {json.dumps(lead_id)} }} }} }};
  if (nm === 'R Person Pick') return {{ item: {{ json: {{ __person_id: {person_id} }} }} }};
  throw new Error('absent ' + nm);
}};
"""


CREATE = N["Body Lead Create"]["parameters"]["jsCode"]
ACT = N["Body Reply Activity"]["parameters"]["jsCode"]
CASES = [
    ("ANDREA: 0 leads + OPEN DEAL -> must NOT create, activity goes to the DEAL",
     2093, False, None, True, "deal"),
    ("no lead, no deal -> creates as before (no regression)",
     None, False, None, False, None),
    ("deal check FAILED -> must NOT create (fail closed on unknown)",
     None, True, None, True, None),
    ("lead exists -> activity still targets the LEAD, deal ignored",
     2093, False, "L1", True, "lead"),
]
for label, did, failed, lid, want_block, want_target in CASES:
    h = harness(did, failed, lid)
    c, err = run(CREATE, h)
    if err:
        print(f"  [FAIL] {label}\n         create: {err}")
        ok = False
        continue
    aj, err2 = run(ACT, h)
    if err2:
        print(f"  [FAIL] {label}\n         activity: {err2}")
        ok = False
        continue
    good = (c.get("__skip") is want_block) and (aj.get("__activity_target") == want_target)
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         create __skip={c.get('__skip')} reason={c.get('__block_reason')!r} · "
          f"activity target={aj.get('__activity_target')!r} "
          f"body_keys={sorted((aj.get('__body') or {}).keys())}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_dealguard_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
AC = after.get("connections") or {}
problems = []
if "R Deal List" not in AN:
    problems.append("R Deal List missing")
if AN.get("R Deal List", {}).get("onError") != "continueRegularOutput":
    problems.append("deal lookup is BLOCKING the reply path")
lr = [c.get("node") for g in (AC.get("Lead Resolve") or {}).get("main", []) for c in (g or [])]
dl = [c.get("node") for g in (AC.get("R Deal List") or {}).get("main", []) for c in (g or [])]
if lr != ["R Deal List"] or dl != ["Merge Reply Ctx"]:
    problems.append(f"chain wrong: Lead Resolve->{lr}, R Deal List->{dl}")
if "$('Lead Resolve').item.json" not in AN["Merge Reply Ctx"]["parameters"]["jsCode"]:
    problems.append("Merge Reply Ctx still reads $json positionally")
if "__blockCreate" not in AN["Body Lead Create"]["parameters"]["jsCode"]:
    problems.append("create guard not live")
if len(after["nodes"]) != len(ORIG["nodes"]) + 1:
    problems.append(f"node count {len(after['nodes'])} != {len(ORIG['nodes'])}+1")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
