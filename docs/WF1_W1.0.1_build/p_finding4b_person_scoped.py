#!/usr/bin/env python3
"""FINDING 4b - replace the offset walk with a PERSON-SCOPED walk over every candidate.

4a (versionId 5fbd32d5) fixed the horizon by paginating /v1/leads over `start`. It works, and its
statics pass, but it is the wrong shape for three measured reasons:

  1. COST / FRAGILITY. 30 pages of 500 rows per reply. Walking it a few times to gather evidence
     rate-limited the whole Pipedrive token (HTTP 429 on every page, backoff exhausted). With
     `onError: continueRegularOutput` a 429 on page 5 of 30 silently truncates the walk, and page
     count alone cannot tell a truncated walk from a complete one.
  2. NOT PROVABLY EXHAUSTIVE. The collection is larger than first measured - paging still returned
     full pages at start=18000 - so the 30-page (15,000) cap may not reach the oldest leads at all.
     A cap whose sufficiency cannot be demonstrated is not a fix, it is a smaller horizon.
  3. IT IS NOT WHAT WAS ASKED FOR. The spec was "query leads for ALL candidate person_ids". That
     was ruled structurally impossible earlier because one request covers one person and fanning
     out would break paired-item resolution - but the pagination scan disproved the premise:
     $('Node').first().json DOES work inside pagination expressions (WF-2S `SL Statistics` and
     WF-2R `SL Leads Statistics` both do it in production). So pagination can iterate CANDIDATES
     instead of offsets: one request per candidate person, no graph change, no fan-out.

Result: 1 request in the common single-person case, N for duplicates, complete at any collection
size, and B27 semantics untouched (Lead Resolve still filters by candidate set and still adopts
whichever duplicate owns the campaign's lead).

Blindness is now COVERAGE, not a page count: saturated means "we did not successfully read every
candidate", so a 429-truncated walk reports itself instead of looking clean.
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
MAX_CANDS = 10

# archived_status is deliberately dropped: it is silently ignored by /v1/leads (all / archived /
# not_archived return byte-identical id sets), so carrying it only implies a capability we do not have.
NEW_URL = ("={{ $('CONFIG').item.json.pd_api }}"
           "{{ '/v1/leads?limit=100&sort=add_time%20DESC' }}")

CANDS_EXPR = "(($('R Person Pick').first().json.__person_candidates) || [])"
PAGINATION = {
    "pagination": {
        "paginationMode": "updateAParameterInEachRequest",
        # one request per candidate person. $pageCount starts at 0, so the FIRST request is already
        # scoped - there is no unscoped page. `|| 0` keeps the person-not-found branch (no
        # candidates) on a harmless query whose result Lead Resolve ignores anyway.
        "parameters": {"parameters": [
            {"type": "qs", "name": "person_id", "value": f"={{{{ {CANDS_EXPR}[$pageCount] || 0 }}}}"}
        ]},
        "paginationCompleteWhen": "other",
        "completeExpression": f"={{{{ $pageCount >= ({CANDS_EXPR}.length - 1) }}}}",
        "limitPagesFetched": True,
        "maxRequests": MAX_CANDS,
        "requestInterval": 150,
    }
}

OLD_SAT = """// saturation now means the PAGE CAP was hit, i.e. leads older than what we fetched may still
// exist. A full walk that ends naturally is complete, and must not report itself as blind.
const saturated = __pages.length >= 30;"""
NEW_SAT = """// Blindness is COVERAGE, not a page count. One request per candidate person means "blind" =
// "a candidate we never successfully read" - the request cap, or a failed page. Pipedrive 429s are
// real (a few evidence-gathering walks exhausted the token), and onError:continueRegularOutput
// turns each one into an item with no .data, which would otherwise look identical to "no leads".
const __errs = __pages.reduce(
  (a, p) => a + ((p && p.json && !Array.isArray(p.json.data)) ? 1 : 0), 0);
const saturated = cand.length ? ((__pages.length - __errs) < cand.length) : false;"""

OLD_OBS = "__lead_pages: __pages.length, __lead_rows: leads.length } }];"
NEW_OBS = ("__lead_pages: __pages.length, __lead_rows: leads.length,\n"
           "                  __lead_read_errors: __errs, __lead_candidates_read:"
           " __pages.length - __errs } }];")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def patch_body(js):
    if "__lead_read_errors" in js:
        return js, False
    for old in (OLD_SAT, OLD_OBS):
        if old not in js:
            raise SystemExit(f"anchor missing, refusing to patch blind:\n{old}")
    return js.replace(OLD_SAT, NEW_SAT).replace(OLD_OBS, NEW_OBS), True


# --------------------------------------------------------------------------------- statics
CFK = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
CAMP = "[Events Visiting] AI4 2026 - Mario - Catch-alls"
NORM = {"campaign_name": CAMP, "campaign_id": 3686184}


def lead(i, person, camp=None, title="x", archived=False):
    return {"id": i, "person_id": person, CFK: camp, "title": title,
            "is_archived": archived, "label_ids": []}


def run_case(js, pages, cands, label, want):
    harness = f"""
const MOCK_PAGES = {json.dumps(pages)};
const MOCK_CAND  = {json.dumps(cands)};
const $input = {{ all: () => MOCK_PAGES.map(p => ({{ json: p }})) }};
const $json = MOCK_PAGES[0] || {{}};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: {{ fields: {{ lead_campaign: {json.dumps(CFK)} }} }} }} }};
  if (nm === 'Normalize') return {{ item: {{ json: {json.dumps(NORM)} }} }};
  if (nm === 'R Person Pick') return {{ item: {{ json: MOCK_CAND }} }};
  throw new Error('node not on this branch: ' + nm);
}};
const __out = (() => {{
{js}
}})();
console.log(JSON.stringify(__out[0].json));
"""
    tmp = os.path.join(HERE, "_f4b_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-240:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"  [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"           {b}")
    return not bad


VICTIM = lead("95d4bfd0", 83437, CAMP, "3686184 - " + CAMP + " - Dan")
CASES = [
    ("single candidate, lead found in its own scoped read (the 2026-07-21 victim)",
     [{"data": [VICTIM]}], {"__person_candidates": [83437]},
     {"__lead_id": "95d4bfd0", "__lead_how": "campaign_field", "__no_lead": False,
      "__leads_page_saturated": False, "__lead_candidates_read": 1, "__lead_read_errors": 0}),
    ("THE ORIGINAL SPEC: 4 duplicates, lead hangs off the 4th -> found and adopted",
     [{"data": []}, {"data": []}, {"data": []}, {"data": [lead("d1", 85506, CAMP)]}],
     {"__person_candidates": [84885, 84886, 84887, 85506]},
     {"__lead_id": "d1", "__person_id": 85506, "__person_adopted": True, "__no_lead": False,
      "__leads_page_saturated": False, "__lead_candidates_read": 4}),
    ("429 on one candidate -> BLIND is reported, not hidden as 'no lead'",
     [{"data": []}, {"error": "429 Too Many Requests"}],
     {"__person_candidates": [84885, 85506]},
     {"__no_lead": True, "__leads_page_saturated": True, "__lead_read_errors": 1,
      "__lead_candidates_read": 1}),
    ("every candidate read, genuinely no lead -> NOT blind (an honest negative)",
     [{"data": []}, {"data": []}], {"__person_candidates": [84885, 85506]},
     {"__no_lead": True, "__leads_page_saturated": False, "__lead_read_errors": 0}),
    ("person-not-found branch: no candidates -> no lead, and NOT reported blind",
     [{"data": [lead("x1", 70000, CAMP)]}], {"__person_candidates": []},
     {"__no_lead": True, "__leads_page_saturated": False}),
    ("stranger guard holds: scoped read cannot return a non-candidate, but if it did -> ignored",
     [{"data": [lead("s1", 70000, CAMP)]}], {"__person_candidates": [83437]},
     {"__lead_id": None, "__no_lead": True}),
    ("archived lead still excluded",
     [{"data": [lead("a1", 83437, CAMP, "x", archived=True)]}], {"__person_candidates": [83437]},
     {"__lead_id": None, "__no_lead": True}),
    ("title-prefix fallback still reached through a scoped read",
     [{"data": [lead("t1", 83437, None, "3686184 - whatever")]}],
     {"__person_candidates": [83437]},
     {"__lead_id": "t1", "__lead_how": "title_prefix", "__no_lead": False}),
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
if not all(run_case(new_js, p, c, lbl, w) for lbl, p, c, w in CASES):
    sys.exit(1)

print("\n--- planned ---")
changes = []
cur_pg = ((listnode["parameters"].get("options") or {}).get("pagination") or {}).get("pagination") or {}
if "person_id" not in json.dumps(cur_pg):
    changes.append(f"R Lead List -> person-scoped, one request per candidate (cap {MAX_CANDS})")
if listnode["parameters"].get("url") != NEW_URL:
    changes.append("R Lead List -> url limit 100, drop the ignored archived_status")
if body_changed:
    changes.append("Lead Resolve -> saturation = coverage shortfall, report read errors")
for c in changes:
    print("  -", c)
if not changes:
    print("  (already applied)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_finding4b_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(wf, indent=2, ensure_ascii=False))

listnode["parameters"]["url"] = NEW_URL
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
if "person_id" not in json.dumps(pg):
    problems.append("pagination does not iterate person_id")
if pg.get("maxRequests") != MAX_CANDS:
    problems.append(f"maxRequests={pg.get('maxRequests')!r}")
if "person_id" in str(an["R Lead List"]["parameters"].get("url")):
    problems.append("person_id hardcoded in the URL (must come from pagination)")
if "__lead_read_errors" not in an["Lead Resolve"]["parameters"]["jsCode"]:
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
