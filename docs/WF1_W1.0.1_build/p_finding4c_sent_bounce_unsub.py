#!/usr/bin/env python3
"""FINDING 4c - the same horizon on SENT / BOUNCE / UNSUB. Authorized by Nik, pre-wave.

Same defect, same fix as 4b (WF-2 cd318c57): `Lead List`, `B Lead List`, `U Lead List` all read one
500-row page, and `Lead Select` / `B Lead Select` / `U Lead Select` all carry byte-identical
`const leads = ($json.data ?? []) || [];` and `>= 500`. SENT's `Lead List` -> `Lead Select` is the
"does a lead already exist?" check, so a lead older than ~7 days is invisible and the branch creates
a SECOND one - a duplicate factory firing on every send.

ONE BRANCH IS NOT LIKE THE OTHERS, and it is the dangerous one:

  B Lead List <- B Lead Ctx      (direct input, already emits __person_candidates)  -> safe to name
  U Lead List <- U Lead Ctx      (direct input, already emits __person_candidates)  -> safe to name
  Lead List   <- IF Have Person Id <- Person Id Final  (emits only __person_id)

SENT's candidates live in `Person Pick`, several hops upstream and NOT on every path to the list
node (the create-person path reaches `Person Id Final` by other routes). Naming a node that did not
execute THROWS inside a pagination expression - and unlike `Lead Select`'s try/catch, an expression
has nowhere to catch it. With onError:continueRegularOutput that throw becomes an empty read, which
`Lead Select` reads as "no existing lead" and the branch CREATES A DUPLICATE. That is strictly worse
than the bug being fixed.

So SENT gets one extra, boring change: `Person Id Final` (a Code node that already reads
`Person Pick` inside a try/catch) carries `__person_candidates` forward. The pagination expression
then names `Person Id Final`, which is the direct ancestor of the list node and therefore always
executed. Fallback for a freshly CREATED person - no candidates, no leads - is __person_id itself.
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

NEW_URL = ("={{ $('CONFIG').item.json.pd_api }}"
           "{{ '/v1/leads?limit=100&sort=add_time%20DESC' }}")

# (list node, select node, node named in the pagination expression)
BRANCHES = [
    ("Lead List", "Lead Select", "Person Id Final"),
    ("B Lead List", "B Lead Select", "B Lead Ctx"),
    ("U Lead List", "U Lead Select", "U Lead Ctx"),
]

CARRY = """
// FINDING 4c: carry the email-verified candidate set forward. `Lead List` paginates one request
// per candidate person, and its pagination expression can only safely name a node that is ALWAYS
// executed on this branch - which `Person Pick` is not (the create-person path bypasses it). This
// node is the list node's direct ancestor, so it is the safe carrier. Empty for a freshly created
// person, which is correct: a new person has no leads.
let __cands = [];
try {
  const __pp = $('Person Pick').item.json;
  if (Array.isArray(__pp.__person_candidates)) __cands = __pp.__person_candidates;
} catch (e) { /* person was created on this run, not searched */ }
"""


def cand_expr(src):
    """candidates if we have them, else the single resolved id - never a throw, never unscoped"""
    j = f"$('{src}').first().json"
    return (f"(({j}.__person_candidates && {j}.__person_candidates.length)"
            f" ? {j}.__person_candidates : [{j}.__person_id])")


def pagination_for(src):
    e = cand_expr(src)
    return {"pagination": {
        "paginationMode": "updateAParameterInEachRequest",
        "parameters": {"parameters": [
            {"type": "qs", "name": "person_id", "value": f"={{{{ {e}[$pageCount] || 0 }}}}"}]},
        "paginationCompleteWhen": "other",
        "completeExpression": f"={{{{ $pageCount >= ({e}.length - 1) }}}}",
        "limitPagesFetched": True,
        "maxRequests": MAX_CANDS,
        "requestInterval": 150,
    }}


OLD_LEADS = "const leads = ($json.data ?? []) || [];"
NEW_LEADS = """// The list node paginates one request per candidate person, so it emits ONE ITEM PER CANDIDATE.
// Reading $json.data would take the first candidate only - which is how the 500-row horizon hid.
const __pages = (() => { try { const a = $input.all(); return (a && a.length) ? a : [{ json: $json }]; }
                         catch (e) { return [{ json: $json }]; } })();
const leads = __pages.reduce((acc, p) => {
  const d = p && p.json && p.json.data;
  return Array.isArray(d) ? acc.concat(d) : acc;
}, []);"""

OLD_SAT = "const saturated = leads.length >= 500;"
NEW_SAT = """// Blindness is COVERAGE, not a row count: "blind" = a candidate we never successfully read,
// via the request cap or a failed page. Pipedrive 429s are real, and onError:continueRegularOutput
// turns each into an item with no .data - otherwise indistinguishable from "this person has no
// leads", which on THIS branch would mean silently creating a duplicate lead.
const __errs = __pages.reduce(
  (a, p) => a + ((p && p.json && !Array.isArray(p.json.data)) ? 1 : 0), 0);
const saturated = cand.length ? ((__pages.length - __errs) < cand.length) : false;"""

OLD_OBS = "__leads_page_saturated: saturated } }];"
NEW_OBS = ("__leads_page_saturated: saturated,\n"
           "                  __lead_pages: __pages.length, __lead_rows: leads.length,\n"
           "                  __lead_read_errors: __errs,\n"
           "                  __lead_candidates_read: __pages.length - __errs } }];")

RET = "return [{ json: {"
RET_NEW = "return [{ pairedItem: { item: 0 }, json: {"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def patch_select(js, name):
    if "__lead_read_errors" in js:
        return js, False
    for old in (OLD_LEADS, OLD_SAT, OLD_OBS):
        if old not in js:
            raise SystemExit(f"{name}: anchor missing, refusing to patch blind:\n  {old}")
    if js.count(RET) != 1:
        raise SystemExit(f"{name}: expected exactly one '{RET}', found {js.count(RET)}")
    return (js.replace(OLD_LEADS, NEW_LEADS).replace(OLD_SAT, NEW_SAT)
              .replace(OLD_OBS, NEW_OBS).replace(RET, RET_NEW), True)


# --------------------------------------------------------------------------------- statics
CFK = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"
CAMP = "[Events Visiting] AI4 2026 - Mario - Catch-alls"
NORM = {"campaign_name": CAMP, "campaign_id": 3686184, "lead": {"email": "x@y.z"}}


def lead(i, person, camp=None, title="x", archived=False):
    return {"id": i, "person_id": person, CFK: camp, "title": title,
            "is_archived": archived, "label_ids": []}


def run_case(js, sel, src, pages, cands, label, want):
    """Mocks only the nodes each body legitimately reaches; anything else throws, so a body that
    depends on a node I did not account for FAILS here rather than in production."""
    harness = f"""
const MOCK_PAGES = {json.dumps(pages)};
const MOCK_CAND  = {json.dumps(cands)};
const $input = {{ all: () => MOCK_PAGES.map(p => ({{ json: p }})) }};
const $json = MOCK_PAGES[0] || {{}};
const CTX = {json.dumps(src)};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: {{ fields: {{ lead_campaign: {json.dumps(CFK)} }} }} }} }};
  if (nm === 'Normalize') return {{ item: {{ json: {json.dumps(NORM)} }} }};
  if (nm === 'Person Id Final') return {{ item: {{ json: {{ ...MOCK_CAND, __org_id: 4242 }} }},
                                          first: () => ({{ json: {{ ...MOCK_CAND, __org_id: 4242 }} }}) }};
  if (nm === CTX || nm === 'Person Pick' || nm === 'B Lead Ctx' || nm === 'U Lead Ctx')
    return {{ item: {{ json: MOCK_CAND }}, first: () => ({{ json: MOCK_CAND }}) }};
  throw new Error('node not on this branch: ' + nm);
}};
const __out = (() => {{
{js}
}})();
console.log(JSON.stringify({{ ...__out[0].json, __paired: !!__out[0].pairedItem }}));
"""
    tmp = os.path.join(HERE, "_f4c_case.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(harness)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"    [FAIL] {label}: {(p.stderr or '').strip()[-240:]}")
        return False
    got = json.loads(p.stdout.strip())
    bad = [f"{k}: want {v!r} got {got.get(k)!r}" for k, v in want.items() if got.get(k) != v]
    print(f"    [{'ok ' if not bad else 'FAIL'}] {label}")
    for b in bad:
        print(f"             {b}")
    return not bad


VICT = lead("95d4bfd0", 83437, CAMP, "3686184 - " + CAMP + " - Dan")
EXISTS = {"Lead Select": "__lead_exists"}


def cases_for(sel):
    """`Lead Select` reports existence as __lead_exists; the R-side reports __no_lead. Both are
    checked through __lead_id, which every branch emits, so the assertions stay branch-agnostic."""
    return [
        ("lead exists on a >7d-old record -> FOUND (no duplicate created)",
         [{"data": [VICT]}], {"__person_candidates": [83437], "__person_id": 83437},
         {"__lead_id": "95d4bfd0", "__lead_how": "campaign_field",
          "__leads_page_saturated": False, "__lead_candidates_read": 1, "__paired": True}),
        ("duplicates: lead hangs off the 4th candidate -> found and adopted",
         [{"data": []}, {"data": []}, {"data": []}, {"data": [lead("d1", 85506, CAMP)]}],
         {"__person_candidates": [84885, 84886, 84887, 85506], "__person_id": 84885},
         {"__lead_id": "d1", "__person_id": 85506, "__person_adopted": True,
          "__lead_candidates_read": 4}),
        ("429 on a candidate -> BLIND reported, so 'no lead' is not trusted into a create",
         [{"data": []}, {"error": "429"}],
         {"__person_candidates": [84885, 85506], "__person_id": 84885},
         {"__lead_id": None, "__leads_page_saturated": True, "__lead_read_errors": 1}),
        ("all candidates read, genuinely no lead -> honest negative, create is correct",
         [{"data": []}, {"data": []}],
         {"__person_candidates": [84885, 85506], "__person_id": 84885},
         {"__lead_id": None, "__leads_page_saturated": False, "__lead_read_errors": 0}),
        ("freshly CREATED person: no candidates, scoped by __person_id -> no lead, not blind",
         [{"data": []}], {"__person_candidates": [], "__person_id": 90001},
         {"__lead_id": None, "__leads_page_saturated": False}),
        ("stranger guard: a non-candidate's lead is ignored",
         [{"data": [lead("s1", 70000, CAMP)]}],
         {"__person_candidates": [83437], "__person_id": 83437}, {"__lead_id": None}),
        ("archived lead stays excluded",
         [{"data": [lead("a1", 83437, CAMP, "x", archived=True)]}],
         {"__person_candidates": [83437], "__person_id": 83437}, {"__lead_id": None}),
        ("title-prefix fallback preserved",
         [{"data": [lead("t1", 83437, None, "3686184 - whatever")]}],
         {"__person_candidates": [83437], "__person_id": 83437},
         {"__lead_id": "t1", "__lead_how": "title_prefix"}),
    ]


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
nodes = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

patched, changes = {}, []
ok = True
for lst, sel, src in BRANCHES:
    js, changed = patch_select(nodes[sel]["parameters"]["jsCode"], sel)
    patched[sel] = (js, changed)
    print(f"\n--- statics: {sel} (paginated by {src}) ---")
    for lbl, pages, cands, want in cases_for(sel):
        ok = run_case(js, sel, src, pages, cands, lbl, want) and ok
if not ok:
    sys.exit(1)

# SENT only: the carrier change that makes naming `Person Id Final` safe
pid_js = nodes["Person Id Final"]["parameters"]["jsCode"]
pid_changed = "__person_candidates" not in pid_js
if pid_changed:
    if "return [{ json: { __person_id: pid, __org_id: org } }];" not in pid_js:
        raise SystemExit("Person Id Final: return anchor missing, refusing to patch blind")
    pid_new = (pid_js.replace("let org = null;", CARRY + "let org = null;")
               .replace("return [{ json: { __person_id: pid, __org_id: org } }];",
                        "return [{ json: { __person_id: pid, __org_id: org,\n"
                        "                  __person_candidates: __cands } }];"))
else:
    pid_new = pid_js

print("\n--- planned ---")
for lst, sel, src in BRANCHES:
    cur = ((nodes[lst]["parameters"].get("options") or {}).get("pagination") or {}).get("pagination") or {}
    if "person_id" not in json.dumps(cur):
        changes.append(f"{lst} -> person-scoped pagination via $('{src}'), cap {MAX_CANDS}")
    if nodes[lst]["parameters"].get("url") != NEW_URL:
        changes.append(f"{lst} -> url limit 100, drop the ignored archived_status")
    if patched[sel][1]:
        changes.append(f"{sel} -> union candidates, coverage saturation, pairedItem pinned")
if pid_changed:
    changes.append("Person Id Final -> carry __person_candidates (makes SENT's expression safe)")
for c in changes:
    print("  -", c)
if not changes:
    print("  (already applied)"); sys.exit(0)
if not a.deploy:
    print("\n--deploy not given: nothing written."); sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_finding4c_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(wf, indent=2, ensure_ascii=False))

for lst, sel, src in BRANCHES:
    nodes[lst]["parameters"]["url"] = NEW_URL
    nodes[lst]["parameters"].setdefault("options", {})["pagination"] = pagination_for(src)
    nodes[sel]["parameters"]["jsCode"] = patched[sel][0]
nodes["Person Id Final"]["parameters"]["jsCode"] = pid_new

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
problems = []
for lst, sel, src in BRANCHES:
    pg = (((an[lst]["parameters"].get("options") or {}).get("pagination") or {})
          .get("pagination") or {})
    if "person_id" not in json.dumps(pg):
        problems.append(f"{lst}: pagination does not iterate person_id")
    if pg.get("maxRequests") != MAX_CANDS:
        problems.append(f"{lst}: maxRequests={pg.get('maxRequests')!r}")
    if f"$('{src}')" not in json.dumps(pg):
        problems.append(f"{lst}: expression does not name {src}")
    if "__lead_read_errors" not in an[sel]["parameters"]["jsCode"]:
        problems.append(f"{sel}: not updated")
if "__person_candidates" not in an["Person Id Final"]["parameters"]["jsCode"]:
    problems.append("Person Id Final: does not carry candidates")
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
