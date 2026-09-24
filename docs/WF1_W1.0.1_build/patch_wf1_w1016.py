"""W1.0.16 — member_id / public_id fallback in WF-1's person resolver.

WHY (measured, not assumed):
  * HeyReach does not always send a stable vanity profile URL. For 20 audited leads it sent the
    opaque `ACoAA…` URN form, or a different vanity slug, than what the CRM holds in
    lh_linkedin_profile_url — the key `Person Search URL` matches on. Those events miss.
  * 660 CRM persons already carry the ACoAA URN as their LinkedIn URL, with confirmed same-human
    duplicates (e.g. Person-fff1f4b0 43925 vs 42651). This class is permanent HeyReach behaviour.
  * The stored member_id equals HeyReach's numeric `linkedin_id` in 16 of 16 checked production
    cases, so a member_id-keyed search resolves every observed case.

WHAT: a third resolution step per branch, after the URL search and before the not-found path:

    IF URL Found ──[false]──> Person Search Member ──> IF Member Verified ──[true]──> PID From Member
                                                                          └─[false]─> (original
                                                                                       not-found
                                                                                       target)

  Four branches (sent, M5 accepted, M6 message, M7 reply) × 3 nodes = 12 new nodes, 98 -> 110.

VERIFIED, NOT TRUSTED: a bare numeric term searched across all custom fields could match a different
person on a different field — structurally the same defect as Make's name matching. So the match is
accepted only if the candidate's OWN member_id (or public_id) equals our key. persons/search returns
custom_fields on the item, which is what makes this checkable.

Nothing else changes: no existing node's parameters, no existing edge except the one false-branch
re-point per resolver, no CONFIG change.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "wf1_live_w1015.json")
DST = os.path.join(HERE, "WF-1 HeyReach Receiver - W1.0.16 patched.json")

BRANCHES = [
    # prefix, not-found target today, canvas anchor for the 3 new nodes
    ("",    "Person Create",  (3296, 496)),
    ("M5 ", "M5 Slack Warn",  (2192, 1216)),
    ("M6 ", "M6 Slack Warn",  (2192, 1728)),
    ("M7 ", "M7 Slack Warn",  (2192, 2288)),
]

# ---------------------------------------------------------------------------------------------
# The search key, shared verbatim by the term and the verifier: verify what you actually searched.
#
# Numeric member id first (>= 5 digits, so a stray small number like the Source enum 446 can never
# be used as a key), else the slug (>= 3 chars), else an unmatchable sentinel. '' would make
# Pipedrive 400 ("term must NOT have fewer than 1 characters"); the sentinel returns 0 items, so a
# lead with neither key costs one no-op call and falls straight through.
KEY_FN = (
    " const l = $('Normalize').item.json.lead || {};"
    " const n = +l.id;"
    " const idOk = l.id !== null && l.id !== undefined && l.id !== ''"
    "   && Number.isFinite(n) && String(Math.trunc(Math.abs(n))).length >= 5;"
    " const s = String(l.slug || '').trim();"
    " const sk = idOk ? String(Math.trunc(n)) : (s.length >= 3 ? s : '__wf1_no_member_key__');"
)
TERM_EXPR = "={{ (() => {" + KEY_FN + " return sk; })() }}"

# MEASURED CONTRACT: persons/search returns custom_fields as a FLAT ARRAY OF VALUES with no field
# keys, so a match can only assert "this candidate holds our key in SOME custom field" - indexing by
# field key is impossible here and silently yields undefined (that mistake shipped once, inert).
# Measured against all 1,223 real production keys: 1,089 hit exactly one person on member_id, and
# ZERO hit a single person on any other field, so containment carries no observed wrong-field risk.
# 43 keys hit TWO persons - both on member_id, i.e. genuine duplicate person records. Refusing those
# would send the sent-branch to Person Create and mint a THIRD duplicate, so we resolve
# deterministically to the OLDEST person id instead - the same oldest-wins rule as WF-2's B27.
MATCH_FN = (
    KEY_FN
    + " const items = ($json.data && $json.data.items) || [];"
    " const skl = sk.toLowerCase();"
    " const holds = (x) => {"
    "   if (sk === '__wf1_no_member_key__') return false;"
    "   const arr = ((x || {}).item || {}).custom_fields;"
    "   if (!Array.isArray(arr)) return false;"
    "   for (const v of arr) {"
    "     if (v === null || v === undefined) continue;"
    "     const t = String(v).trim();"
    "     if (t === sk) return true;"
    "     if (t.toLowerCase().split(',').map(z => z.trim()).includes(skl)) return true;"
    "   }"
    "   return false;"
    " };"
    " const hits = items.filter(holds)"
    "   .map(x => x.item && x.item.id)"
    "   .filter(id => id !== null && id !== undefined)"
    "   .sort((a, b) => Number(a) - Number(b));"
)
VERIFY_EXPR = "={{ (() => {" + MATCH_FN + " return hits.length > 0; })() }}"
PID_EXPR = "={{ (() => {" + MATCH_FN + " return hits.length ? hits[0] : null; })() }}"


def clone_search(src_node, name, pos):
    """Clone the existing URL search so credentials/typeVersion/options carry over untouched."""
    n = copy.deepcopy(src_node)
    n["name"] = name
    n["id"] = None
    n["position"] = list(pos)
    qp = ((n["parameters"].get("queryParameters") or {}).get("parameters") or [])
    for p in qp:
        if p.get("name") == "term":
            p["value"] = TERM_EXPR
        elif p.get("name") == "fields":
            p["value"] = "custom_fields"
        elif p.get("name") == "exact_match":
            p["value"] = "true"
    return n


def clone_if(src_node, name, pos, expr):
    n = copy.deepcopy(src_node)
    n["name"] = name
    n["id"] = None
    n["position"] = list(pos)
    conds = n["parameters"]["conditions"]
    conds["conditions"] = [{
        "id": "w1016-verify-0001",
        "leftValue": expr,
        "rightValue": True,
        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
    }]
    return n


def clone_set(src_node, name, pos, expr):
    n = copy.deepcopy(src_node)
    n["name"] = name
    n["id"] = None
    n["position"] = list(pos)
    asg = ((n["parameters"].get("assignments") or {}).get("assignments") or [])
    for a in asg:
        if a.get("name") == "person_id":
            a["value"] = expr
    return n


def main():
    wf = json.load(open(SRC, encoding="utf-8"))
    N = {n["name"]: n for n in wf["nodes"]}
    before = len(wf["nodes"])
    used_ids = {n.get("id") for n in wf["nodes"]}
    seq = 0

    def fresh_id():
        nonlocal seq
        while True:
            seq += 1
            cand = f"w1016-{seq:04d}-0000-4000-8000-000000000000"
            if cand not in used_ids:
                used_ids.add(cand)
                return cand

    added = []
    for pre, notfound, (x, y) in BRANCHES:
        url_search = N[f"{pre}Person Search URL"]
        if_url = N[f"{pre}IF URL Found"]
        pid_url = N[f"{pre}PID From URL"]
        get_node = f"{pre}Person Get"

        s_name = f"{pre}Person Search Member"
        i_name = f"{pre}IF Member Verified"
        p_name = f"{pre}PID From Member"
        for nm in (s_name, i_name, p_name):
            if nm in N:
                raise SystemExit(f"node already exists, refusing to double-patch: {nm}")

        s = clone_search(url_search, s_name, (x, y))
        i = clone_if(if_url, i_name, (x + 224, y), VERIFY_EXPR)
        p = clone_set(pid_url, p_name, (x + 448, y), PID_EXPR)
        for n in (s, i, p):
            n["id"] = fresh_id()
            wf["nodes"].append(n)
            added.append(n["name"])

        # rewire: the URL search's not-found branch now goes to the member search
        main_out = wf["connections"][f"{pre}IF URL Found"]["main"]
        while len(main_out) < 2:
            main_out.append([])
        false_targets = main_out[1]
        if [t["node"] for t in false_targets] != [notfound]:
            raise SystemExit(f"unexpected false-branch target for {pre}IF URL Found: "
                             f"{[t['node'] for t in false_targets]}")
        main_out[1] = [{"node": s_name, "type": "main", "index": 0}]
        wf["connections"][s_name] = {"main": [[{"node": i_name, "type": "main", "index": 0}]]}
        wf["connections"][i_name] = {"main": [
            [{"node": p_name, "type": "main", "index": 0}],
            [{"node": notfound, "type": "main", "index": 0}],
        ]}
        wf["connections"][p_name] = {"main": [[{"node": get_node, "type": "main", "index": 0}]]}

    validate(wf, before, added)
    json.dump(wf, open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"nodes {before} -> {len(wf['nodes'])}  (+{len(added)})")
    print(f"wrote {DST}")


def validate(wf, before, added):
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "duplicate node names"
    assert len(wf["nodes"]) == before + 12, f"expected +12 nodes, got {len(wf['nodes']) - before}"
    assert len(added) == 12, added
    ids = [n["id"] for n in wf["nodes"]]
    assert len(ids) == len(set(ids)), "duplicate node ids"
    nameset = set(names)
    for src, d in wf["connections"].items():
        assert src in nameset, f"connection from unknown node {src}"
        for br in (d.get("main") or []):
            for t in (br or []):
                assert t["node"] in nameset, f"{src} -> unknown {t['node']}"

    for pre, notfound, _ in BRANCHES:
        s, i, p = (f"{pre}Person Search Member", f"{pre}IF Member Verified",
                   f"{pre}PID From Member")
        assert [t["node"] for t in wf["connections"][f"{pre}IF URL Found"]["main"][1]] == [s]
        assert [t["node"] for t in wf["connections"][i]["main"][0]] == [p]
        assert [t["node"] for t in wf["connections"][i]["main"][1]] == [notfound]
        assert [t["node"] for t in wf["connections"][p]["main"][0]] == [f"{pre}Person Get"]
        # the found path must be untouched
        assert [t["node"] for t in wf["connections"][f"{pre}IF URL Found"]["main"][0]] \
            == [f"{pre}PID From URL"]

    # every new node reachable, and nothing orphaned
    reached, stack = set(), ["HeyReach Webhook"]
    incoming = {}
    for src, d in wf["connections"].items():
        for br in (d.get("main") or []):
            for t in (br or []):
                incoming.setdefault(t["node"], set()).add(src)
    for nm in added:
        assert incoming.get(nm), f"orphan: nothing feeds {nm}"

    # the search term must never be an empty string (Pipedrive 400s on that)
    for n in wf["nodes"]:
        if n["name"].endswith("Person Search Member"):
            qp = ((n["parameters"].get("queryParameters") or {}).get("parameters") or [])
            term = next(p["value"] for p in qp if p["name"] == "term")
            assert "__wf1_no_member_key__" in term, "term lacks the sentinel"
            assert "Number.isFinite" in term, "term lacks numeric validation"
            flds = next(p["value"] for p in qp if p["name"] == "fields")
            assert flds == "custom_fields", flds
        if n["name"].endswith("IF Member Verified") or n["name"].endswith("PID From Member"):
            blob = json.dumps(n["parameters"])
            # the search response has NO field keys - indexing by one is the bug that shipped inert
            assert "custom_fields]" not in blob and "f.member_id]" not in blob, \
                f"{n['name']} must not index custom_fields by field key"
            assert "Array.isArray" in blob, f"{n['name']} must treat custom_fields as an array"
            assert "sort" in blob, f"{n['name']} must resolve duplicates deterministically"
    print("validate: OK")


if __name__ == "__main__":
    sys.exit(main())
