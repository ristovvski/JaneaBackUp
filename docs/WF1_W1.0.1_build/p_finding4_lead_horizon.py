#!/usr/bin/env python3
"""FINDING 4 - reply-side lead resolution can only see the newest 500 leads.

WHAT THE EVIDENCE ACTUALLY SAYS (the original scoping was wrong, and so was my first diagnosis):

  * `R Lead List` reads /v1/leads?limit=500&sort=add_time DESC. That page spans 2026-08-11 ->
    2026-08-04. There are >=6,000 live leads, oldest 2026-07-03: **92%+ are invisible.**
  * 23 of the last 34 reply executions that reached `Lead Resolve` returned __no_lead, and EVERY
    one carried __leads_page_saturated=True.
  * Three of those people demonstrably have live leads (pii-4acbb413@example.invalid 95d4bfd0,
    pii-840d936c@example.invalid df711600, pii-ebd365bc@example.invalid b8c00640) - all added 2026-07-21, all
    outside the window. Their CRM updates were dropped by the horizon.
  * The fixture lead 72ec85c0 is a red herring: it is ARCHIVED. `Lead Resolve` filters archived
    leads by design, so lead=None in the live proof was CORRECT behaviour, not this defect.
  * `archived_status` is silently IGNORED by /v1/leads - all / archived / not_archived return
    byte-identical id sets with zero archived rows. Archived leads are unreachable from any list
    read, so the parameter in the URL is decorative and the !is_archived filter is belt-and-braces.

WHY NOT PERSON-SCOPING, AS ORIGINALLY SCOPED:
  /v1/leads?person_id=A,B and repeated person_id= both return HTTP 400 - one request covers exactly
  one person. Covering every __person_candidate therefore needs N requests, i.e. fanning
  `R Person Verify Apply` out to N items. That node also feeds `IF Person Deleted` (the deleted-
  person warning would fire N times) and four nodes reach back to it with $('R Person Verify
  Apply').item, which breaks on multi-item pairing. That is graph surgery - P0-1b's gate class.
  Scoping to the PRIMARY candidate only would be worse than today: `Lead Resolve` adopts whichever
  duplicate actually owns the lead, so primary-only scoping REGRESSES the duplicate case.

THE FIX (parameters + one code body, no graph change, strict superset of today's data):
  1. `R Lead List` gains offset pagination: start = $pageCount * 500, stop when a page returns
     < 500 rows, hard cap 30 requests (15,000 leads).
  2. `Lead Resolve` unions the pages. n8n emits ONE ITEM PER PAGE - reading $json.data would use
     page 1 only, which IS today's horizon (the same lesson that broke WF-2S `Carry Campaign`).
     Saturation now means "the page cap was hit", which is the honest meaning.
  Every B27 rule - candidate-set membership, campaign-field match, title-prefix fallback,
  oldest-wins provisional, person adoption - is byte-identical. Only the input set grows.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
PAGE, MAX_PAGES = 500, 30

# n8n's pagination option is a fixedCollection: options.pagination.pagination.{...}. Writing the
# inner object straight onto options.pagination type-checks fine, survives the PUT, and is then
# SILENTLY IGNORED - the node keeps fetching one page. Verified against the two nodes in this
# instance that actually paginate (WF-2S `SL Statistics`, WF-2R `SL Leads Statistics`, both 4.2).
PAGINATION = {
    "pagination": {
        "paginationMode": "updateAParameterInEachRequest",
        "parameters": {"parameters": [
            {"type": "qs", "name": "start", "value": f"={{{{ $pageCount * {PAGE} }}}}"}
        ]},
        "paginationCompleteWhen": "other",
        # Pipedrive returns data:[] past the end; a short page also means the end. Length is used
        # rather than additional_data.pagination.more_items_in_collection because a missing
        # additional_data would make the expression undefined and never complete.
        "completeExpression": f"={{{{ (($response.body || {{}}).data || []).length < {PAGE} }}}}",
        "limitPagesFetched": True,
        "maxRequests": MAX_PAGES,
        "requestInterval": 250,
    }
}

OLD_LEADS = "const leads = ($json.data ?? []) || [];"
NEW_LEADS = """// `R Lead List` paginates, so it emits ONE ITEM PER PAGE. Reading $json.data would take page 1
// only - which is exactly the 500-row horizon this change exists to remove (the same shape that
// broke WF-2S `Carry Campaign`). Error items from onError:continueRegularOutput carry no .data and
// are skipped rather than thrown on.
const __pages = (() => { try { const a = $input.all(); return (a && a.length) ? a : [{ json: $json }]; }
                         catch (e) { return [{ json: $json }]; } })();
const leads = __pages.reduce((acc, p) => {
  const d = p && p.json && p.json.data;
  return Array.isArray(d) ? acc.concat(d) : acc;
}, []);"""

OLD_SAT = "const saturated = leads.length >= 500;"
NEW_SAT = f"""// saturation now means the PAGE CAP was hit, i.e. leads older than what we fetched may still
// exist. A full walk that ends naturally is complete, and must not report itself as blind.
const saturated = __pages.length >= {MAX_PAGES};"""

OLD_RET = "return [{ json: { __lead: hit,"
NEW_RET = "return [{ pairedItem: { item: 0 }, json: { __lead: hit,"

# Without these, a live execution cannot distinguish "paginated 12 pages and the lead genuinely
# does not exist" from "pagination was silently ignored, we saw 500 rows again" - the exact blind
# spot that made the flattened config look healthy. Coverage gets printed, not inferred.
OLD_OBS = "__leads_page_saturated: saturated } }];"
NEW_OBS = ("__leads_page_saturated: saturated,\n"
           "                  __lead_pages: __pages.length, __lead_rows: leads.length } }];")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def patch_body(js):
    """Idempotent: the two halves of this fix (node pagination, body union) can land in separate
    PUTs, so a re-run must repair only what is missing. An already-patched body is returned as-is
    and still goes through the statics - the tests run against whatever will actually be live."""
    changed = False
    if "__pages" not in js:
        for old in (OLD_LEADS, OLD_SAT, OLD_RET):
            if old not in js:
                raise SystemExit(f"anchor missing, refusing to patch blind:\n  {old}")
        js = js.replace(OLD_LEADS, NEW_LEADS).replace(OLD_SAT, NEW_SAT).replace(OLD_RET, NEW_RET)
        changed = True
    if "__lead_rows" not in js:
        if OLD_OBS not in js:
            raise SystemExit(f"anchor missing, refusing to patch blind:\n  {OLD_OBS}")
        js = js.replace(OLD_OBS, NEW_OBS)
        changed = True
    return js, changed


# ---------------------------------------------------------------- statics (EXECUTE the real body)
CFK = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
CAMP = "[Events Visiting] AI4 2026 - Mario - Catch-alls"


def lead(i, person, camp_field=None, title="x", archived=False):
    return {"id": i, "person_id": person, CFK: camp_field, "title": title,
            "is_archived": archived, "label_ids": []}


def page(rows):
    return {"data": rows}


def filler(n, start=0):
    return [lead(f"f{start + i}", 999000 + i) for i in range(n)]


def run_case(js, pages, cands, norm, label, want):
    harness = f"""
const MOCK_PAGES = {json.dumps(pages)};
const MOCK_CAND  = {json.dumps(cands)};
const MOCK_NORM  = {json.dumps(norm)};
const $input = {{ all: () => MOCK_PAGES.map(p => ({{ json: p }})) }};
const $json = MOCK_PAGES[0] || {{}};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: {{ fields: {{ lead_campaign: {json.dumps(CFK)} }} }} }} }};
  if (nm === 'Normalize') return {{ item: {{ json: MOCK_NORM }} }};
  if (nm === 'R Person Pick') return {{ item: {{ json: MOCK_CAND }} }};
  throw new Error('node not on this branch: ' + nm);   // Apply Enrich etc.
}};
const __out = (() => {{
{js}
}})();
console.log(JSON.stringify({{ ...__out[0].json, __paired: !!__out[0].pairedItem }}));
"""
    tmp = os.path.join(HERE, "_leadresolve_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-260:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return not bad


NORM = {"campaign_name": CAMP, "campaign_id": 3686184}
# the real victim: person 83437's lead sits on page 8 of a 12-page walk, invisible to page 1
VICTIM = lead("95d4bfd0", 83437, CAMP, "3686184 - " + CAMP + " - Dan")
OLD_ONLY_PAGE = [page(filler(PAGE))]
FULL_WALK = [page(filler(PAGE, i * PAGE)) for i in range(7)] + \
            [page(filler(PAGE - 1, 7 * PAGE) + [VICTIM])] + \
            [page(filler(PAGE, i * PAGE)) for i in range(8, 11)] + [page(filler(10, 99000))]

CASES = [
    ("OLD-BUILD FAILURE CASE reproduced: victim beyond page 1 -> no lead",
     OLD_ONLY_PAGE, {"__person_candidates": [83437]}, NORM,
     {"__lead_id": None, "__lead_how": "none", "__no_lead": True}),
    ("FIXED: same victim found on page 8 of the full walk",
     FULL_WALK, {"__person_candidates": [83437]}, NORM,
     {"__lead_id": "95d4bfd0", "__lead_how": "campaign_field", "__no_lead": False,
      "__leads_page_saturated": False, "__paired": True,
      # coverage is REPORTED, so a live run proves it walked rather than leaving me to infer it
      "__lead_pages": 12, "__lead_rows": 12 * PAGE - PAGE + 10}),
    ("normal case unchanged: lead on page 1 still resolves",
     [page([VICTIM] + filler(10))], {"__person_candidates": [83437]}, NORM,
     {"__lead_id": "95d4bfd0", "__lead_how": "campaign_field", "__no_lead": False}),
    ("title-prefix fallback still works across pages",
     [page(filler(PAGE)), page([lead("t1", 83437, None, "3686184 - whatever")])],
     {"__person_candidates": [83437]}, NORM,
     {"__lead_id": "t1", "__lead_how": "title_prefix", "__no_lead": False}),
    ("B27 duplicates: lead hangs off the NEWEST duplicate, on a later page -> adopted",
     [page(filler(PAGE)), page([lead("d1", 85506, CAMP)])],
     {"__person_candidates": [84885, 84886, 84887, 85506]}, NORM,
     {"__lead_id": "d1", "__person_id": 85506, "__person_adopted": True, "__no_lead": False}),
    ("B27 stranger guard: same campaign, person NOT ours -> still no lead",
     [page(filler(PAGE)), page([lead("s1", 70000, CAMP)])],
     {"__person_candidates": [83437]}, NORM,
     {"__lead_id": None, "__no_lead": True}),
    ("archived lead stays excluded (they never reach a list read anyway)",
     [page([lead("a1", 83437, CAMP, "x", archived=True)])],
     {"__person_candidates": [83437]}, NORM,
     {"__lead_id": None, "__no_lead": True}),
    ("no candidates (person-not-found branch) -> no lead, no crash",
     FULL_WALK, {"__person_candidates": []}, NORM,
     {"__lead_id": None, "__no_lead": True}),
    ("page cap hit -> saturation reported honestly",
     [page(filler(PAGE, i * PAGE)) for i in range(MAX_PAGES)],
     {"__person_candidates": [83437]}, NORM,
     {"__leads_page_saturated": True, "__no_lead": True}),
    ("onError error item (no .data) is skipped, not thrown on",
     [{"error": "ECONNRESET"}, page([VICTIM])], {"__person_candidates": [83437]}, NORM,
     {"__lead_id": "95d4bfd0", "__no_lead": False}),
]

ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
nodes = {n["name"]: n for n in wf["nodes"]}
resolve, listnode = nodes["Lead Resolve"], nodes["R Lead List"]
new_js, body_changed = patch_body(resolve["parameters"]["jsCode"])

print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")
print(f"\n--- statics: executing the PATCHED Lead Resolve body ({len(CASES)} cases) ---")
if not all(run_case(new_js, p, c, n, lbl, w) for lbl, p, c, n, w in CASES):
    sys.exit(1)

print("\n--- planned ---")
changes = []
# truthiness of options.pagination is NOT the test - a malformed (flattened) value is truthy and
# does nothing. The test is whether the value n8n actually reads is in place.
_cur = ((listnode["parameters"].get("options") or {}).get("pagination") or {}).get("pagination")
if not isinstance(_cur, dict) or _cur.get("maxRequests") != MAX_PAGES:
    changes.append(f"R Lead List -> offset pagination, {PAGE}/page, cap {MAX_PAGES}")
if body_changed:
    changes.append("Lead Resolve -> union pages, honest saturation, pairedItem pinned")
else:
    print("  (Lead Resolve already carries the union - statics above ran against the LIVE body)")
for c in changes:
    print("  -", c)
if not changes:
    print("  (already applied)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_finding4_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(wf, indent=2, ensure_ascii=False))

listnode["parameters"].setdefault("options", {})["pagination"] = PAGINATION
resolve["parameters"]["jsCode"] = new_js

was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
try:
    n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
finally:
    if was:
        n8n(f"/api/v1/workflows/{WF2}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2}")
an = {x["name"]: x for x in after["nodes"]}
pg = (((an["R Lead List"]["parameters"].get("options") or {}).get("pagination") or {})
      .get("pagination") or {})
problems = []
if not pg:
    problems.append("pagination absent (or flattened) after PUT")
else:
    if pg.get("maxRequests") != MAX_PAGES:
        problems.append(f"maxRequests={pg.get('maxRequests')!r}")
    if pg.get("paginationMode") != "updateAParameterInEachRequest":
        problems.append(f"paginationMode={pg.get('paginationMode')!r}")
    if str(PAGE) not in str(pg.get("completeExpression")):
        problems.append(f"completeExpression={pg.get('completeExpression')!r}")
if "__pages" not in an["Lead Resolve"]["parameters"]["jsCode"]:
    problems.append("Lead Resolve not updated")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')} (was {was})")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])}")
sys.exit(1 if problems else 0)
