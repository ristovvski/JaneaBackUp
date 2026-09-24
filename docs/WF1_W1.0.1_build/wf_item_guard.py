"""Fan-out-aware guard for backward `.item` lookups (the S1 defect class).

WHY THIS IS NOT A BLANKET BAN
`$('X').item` is perfectly correct in a workflow where every node handles exactly one item — WF-2 is
built that way (one webhook payload per execution) and uses it in dozens of places, proven over
thousands of live executions. The defect only exists DOWNSTREAM OF A FAN-OUT: once a node emits N
items, n8n cannot resolve which upstream item a later node is paired with, and `.item` throws
"Paired item data for item from node 'X' is unavailable".

That exact error crashed WF-2S cycle 1 and has made WF-2H fail every single run it ever attempted.
So the guard models the graph:

  1. find FAN-OUT sources - nodes that can emit more items than they consumed
  2. propagate "multi" downstream through the connection graph
  3. flag any `$('X').item` used by a node inside the multi region

Fan-out detection is deliberately conservative about what counts as 1:1. `$input.all().map(...)`
preserves item count and is NOT a fan-out; `rows.map(...)` over a parsed API array IS.

Usage:
    python wf_item_guard.py sweep            # check every built workflow on disk
    python wf_item_guard.py check <file.json>

Import in a builder's validate():
    from wf_item_guard import violations
    for v in violations(wf): e.append(v)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

# Built artifacts to sweep. WF-1 is included for AWARENESS ONLY - it is frozen and never patched
# from here; the sweep reports it so we know whether the class exists there at all.
SWEEP = [
    ("WF-2  Smartlead Receiver", HERE / "WF-2 Smartlead Receiver - built.json", "enforce"),
    ("WF-2S SENT Reconciler", HERE / "wf1-release-evidence" / "wf2s-built.json", "enforce"),
    ("WF-2H Health & Digest", HERE / "wf1-release-evidence" / "wf2h-built.json", "enforce"),
    ("WF-1  HeyReach Receiver", HERE / "wf1-release-evidence" / "wf1-built.json", "report-only"),
]

def item_lookups(blob):
    """Node names referenced via a backward `$('X').item` lookup.

    Written as a scan rather than a regex: the pattern has to survive a Python source string, a JSON
    dump and a shell heredoc, and an escaping slip made it silently match NOTHING - which reported
    every workflow clean, including one I knew was broken. A scan cannot fail quietly.
    """
    found = []
    for quote in ("'", '"'):
        needle = ")" + ".item"
        idx = 0
        while True:
            k = blob.find(needle, idx)
            if k < 0:
                break
            idx = k + 1
            head = blob[:k]
            open_at = head.rfind("$(" + quote)
            if open_at < 0:
                continue
            # "$(" is 2 chars, then the opening quote - the name starts after all three
            name = head[open_at + 2 + len(quote):]
            # strip the trailing quote that closes the node name
            if name.endswith(quote):
                name = name[:-1]
            if name and quote not in name and len(name) < 60:
                found.append(name)
    return found


# Only the RETURN statement decides how many items a Code node emits. An earlier version of this
# guard matched any `.map(` anywhere in the body and declared WF-2 a 162-violation disaster - but
# WF-2 has run correctly in production for thousands of executions. `mails.map(...)` inside
# Person Pick is a value-level map, not a fan-out. Calibration targets, both empirical:
#   WF-2  must come out CLEAN (single-item webhook chain, .item proven correct live)
#   WF-2H must come out DIRTY (it has failed literally every run with this exact error)
RETURN_RE = re.compile(r"return\s+([^;]+);", re.S)



def top_level_returns(js):
    """`return` expressions at the node body's TOP level only.

    A nested `return` belongs to a helper function and says nothing about how many items the NODE
    emits. Matching them made the guard call a picker a fan-out because of
    `return j.__person_candidates.map(String)` inside an IIFE - and that one false positive put all
    183 of WF-2's legitimate .item lookups into the danger zone and blocked the build.
    """
    out, depth, i, n = [], 0, 0, len(js)
    while i < n:
        ch = js[i]
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        elif depth == 0 and js.startswith("return", i) and (i == 0 or not js[i - 1].isalnum()):
            j = i + len("return")
            # capture to the terminating semicolon, tracking nesting so inner ; are ignored
            d2, k = 0, j
            while k < n:
                c = js[k]
                if c in "{([":
                    d2 += 1
                elif c in "})]":
                    d2 -= 1
                elif c == ";" and d2 <= 0:
                    break
                k += 1
            out.append(js[j:k].strip())
            i = k
        i += 1
    return out


def _code(n):
    return str((n.get("parameters") or {}).get("jsCode") or "")


def _params_blob(n):
    return json.dumps(n.get("parameters") or {}, ensure_ascii=False)


def emits_multiple(node):
    """True when this node can emit MORE THAN ONE item without preserving pairing.

    n8n resolves `.item` by walking pairedItem. A Code node that returns freshly built objects sets
    no pairedItem - but when it emits exactly one item n8n can still infer the pairing, which is why
    single-item chains work. The break happens only when several unpaired items flow onward.
    """
    t = node.get("type", "")
    if t in ("n8n-nodes-base.splitOut", "n8n-nodes-base.itemLists"):
        return True
    if t != "n8n-nodes-base.code":
        return False
    js = _code(node)
    # an explicit pairedItem keeps the chain resolvable no matter how many items are emitted
    if "pairedItem" in js:
        return False
    for expr in top_level_returns(js):
        # A single literal item is ONE item no matter what appears inside it. The earlier rule
        # ("[" and no .map anywhere) produced 183 false positives the moment a picker built a
        # value with cands.map(c => c.id) inside its returned object - it declared WF-2, which
        # runs correctly in production, a fan-out. What decides the count is the number of
        # TOP-LEVEL elements in the returned array, not the expressions inside them.
        if expr.startswith("["):
            flat = re.sub(r"\s+", "", expr)
            if "},{" not in flat:          # a one-element array literal
                continue
        # mapping over the node's own input is strictly 1:1
        if re.match(r"^\$input\.all\(\)\s*\.map\(", expr):
            continue
        if ".map(" in expr or ".flatMap(" in expr:
            # X.map(...) over anything other than $input.all() can emit a different count
            recv = expr.split(".map(")[0].split(".flatMap(")[0].strip()
            if recv and not recv.startswith("$input.all()"):
                # a variable that was itself assigned straight from $input.all() is still 1:1
                if not re.search(r"(const|let|var)\s+" + re.escape(recv) + r"\s*=\s*\$input\.all\(\)\s*;",
                                 js):
                    return True
            continue
        # `return out;` / `return batch;` - an accumulator that can hold many rows
        if re.match(r"^[A-Za-z_$][\w$]*$", expr):
            if re.search(r"(const|let|var)\s+" + re.escape(expr) + r"\s*=\s*\[\s*\]", js):
                return True
    return False


def is_fanout(node):
    return emits_multiple(node)


def multi_region(wf):
    """Node names that may be handling one of several items (fan-out already happened upstream)."""
    conns = wf.get("connections") or {}
    fan = {n["name"] for n in wf["nodes"] if is_fanout(n)}
    # BFS downstream from every fan-out source; the source itself emits N so everything after is multi
    multi, frontier = set(), list(fan)
    while frontier:
        cur = frontier.pop()
        for branch in (conns.get(cur, {}).get("main") or []):
            for c in (branch or []):
                nm = c.get("node")
                if nm and nm not in multi:
                    multi.add(nm)
                    frontier.append(nm)
    return fan, multi


def violations(wf):
    """List of human-readable violations; empty when clean."""
    fan, multi = multi_region(wf)
    out = []
    for n in wf["nodes"]:
        if n["name"] not in multi:
            continue
        blob = _params_blob(n)
        for src in item_lookups(blob):
            out.append(f"{n['name']}: backward $('{src}').item inside a fan-out region "
                       f"(S1 class) - use .first() for singletons or .all() + index")
    # dedupe repeats of the same (node, source)
    return sorted(set(out))


def report(label, path, mode):
    if not path.exists():
        print(f"{label:<28} SKIP - artifact not on disk ({path.name})")
        return None
    wf = json.loads(path.read_text(encoding="utf-8-sig"))
    fan, multi = multi_region(wf)
    v = violations(wf)
    print(f"\n{label}   [{mode}]   {path.name}")
    print(f"   nodes={len(wf['nodes'])}  fan-out sources={sorted(fan) or 'none'}")
    print(f"   multi region: {len(multi)} node(s)")
    if v:
        print(f"   VIOLATIONS ({len(v)}):")
        for x in v:
            print(f"      - {x}")
    else:
        print("   clean: no backward .item inside any fan-out region")
    # also report .item usage OUTSIDE the multi region, purely informational
    outside = 0
    for n in wf["nodes"]:
        if n["name"] in multi:
            continue
        outside += len(item_lookups(_params_blob(n)))
    print(f"   (.item used {outside}x outside any fan-out region - legitimate, single-item chain)")
    return v


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check" and len(sys.argv) > 2:
        v = report("workflow", Path(sys.argv[2]), "enforce")
        return 1 if v else 0
    print("=" * 100)
    print("S1 CLASS SWEEP - backward .item inside a fan-out region")
    print("=" * 100)
    failed = False
    for label, path, mode in SWEEP:
        v = report(label, path, mode)
        if v and mode == "enforce":
            failed = True
    print()
    print("VERDICT:", "CARRIERS REMAIN (enforced artifacts)" if failed else "no carriers in enforced artifacts")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
