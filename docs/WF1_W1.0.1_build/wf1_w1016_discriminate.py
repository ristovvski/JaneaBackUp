"""Mutation proof for the W1.0.16 suite. Every mutant must APPLY and must be CAUGHT."""
import json
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
TARGET = BUILD / "WF-1 HeyReach Receiver - W1.0.16 patched.json"
TESTS = BUILD / "wf1_w1016_static_tests.js"
MUTANTS = []


def mutant(label, expect):
    def deco(fn):
        MUTANTS.append((label, expect, fn))
        return fn
    return deco


def node(wf, name):
    return next(n for n in wf["nodes"] if n["name"] == name)


def qp(wf, name, key):
    for p in node(wf, name)["parameters"]["queryParameters"]["parameters"]:
        if p["name"] == key:
            return p
    raise KeyError(key)


def verify_cond(wf, name):
    return node(wf, name)["parameters"]["conditions"]["conditions"][0]


def pid_asg(wf, name):
    for a in node(wf, name)["parameters"]["assignments"]["assignments"]:
        if a["name"] == "person_id":
            return a
    raise KeyError("person_id")


@mutant("term loses the sentinel -> an empty term reaches Pipedrive (400)", "T4")
def m1(wf):
    p = qp(wf, "Person Search Member", "term")
    p["value"] = p["value"].replace("'__wf1_no_member_key__')", "'')")


@mutant("term drops numeric validation -> NaN leaks into the search", "T5")
def m2(wf):
    p = qp(wf, "Person Search Member", "term")
    p["value"] = ("={{ (() => { const l = $('Normalize').item.json.lead || {};"
                  " return String(+l.id); })() }}")


@mutant("THE MAKE DISEASE: verify accepts any hit without checking ownership", "V4")
def m3(wf):
    c = verify_cond(wf, "IF Member Verified")
    c["leftValue"] = ("={{ ((($json.data && $json.data.items) || []).length > 0) }}")


@mutant("pid takes items[0] blindly instead of the verified candidate", "V7")
def m4(wf):
    a = pid_asg(wf, "PID From Member")
    a["value"] = "={{ $json.data.items[0].item.id }}"


@mutant("key drops the slug fallback -> the slug-variant cases regress", "V3")
def m5(wf):
    for nm, get in (("Person Search Member", None), ("IF Member Verified", verify_cond),
                    ("PID From Member", pid_asg)):
        obj = qp(wf, nm, "term") if get is None else get(wf, nm)
        fld = "value" if get is None else ("leftValue" if get is verify_cond else "value")
        obj[fld] = obj[fld].replace(
            "(s.length >= 3 ? s : '__wf1_no_member_key__')", "'__wf1_no_member_key__'")


@mutant("key drops the numeric member id -> the URN cases regress", "V1")
def m6(wf):
    for nm, get in (("Person Search Member", None), ("IF Member Verified", verify_cond),
                    ("PID From Member", pid_asg)):
        obj = qp(wf, nm, "term") if get is None else get(wf, nm)
        fld = "value" if get is None else ("leftValue" if get is verify_cond else "value")
        obj[fld] = obj[fld].replace("const idOk = l.id !== null", "const idOk = false && l.id !== null")


@mutant("the key is matched by substring instead of equality", "V10")
def m7(wf):
    c = verify_cond(wf, "IF Member Verified")
    c["leftValue"] = c["leftValue"].replace("if (t === sk) return true;",
                                           "if (t.includes(sk)) return true;")


@mutant("REGRESSION GUARD: verifier indexes custom_fields by field key (the shipped-inert bug)",
        "V14")
def m18(wf):
    c = verify_cond(wf, "IF Member Verified")
    c["leftValue"] = ("={{ (() => { const f = $('CONFIG').item.json.fields;"
                      " const l = $('Normalize').item.json.lead || {};"
                      " const items = ($json.data && $json.data.items) || [];"
                      " return items.some(x => String(((((x||{}).item)||{}).custom_fields||{})"
                      "[f.member_id]) === String(l.id)); })() }}")


@mutant("duplicates resolved by response order instead of oldest-id", "V15")
def m19(wf):
    a = pid_asg(wf, "PID From Member")
    a["value"] = a["value"].replace(".sort((a, b) => Number(a) - Number(b))", "")


@mutant("short-id guard removed -> a tiny number (Source=446) becomes a search key", "V16")
def m20(wf):
    p = qp(wf, "Person Search Member", "term")
    p["value"] = p["value"].replace(".length >= 5", ".length >= 1")


@mutant("slug length guard removed", "V17")
def m21(wf):
    p = qp(wf, "Person Search Member", "term")
    p["value"] = p["value"].replace("s.length >= 3", "s.length >= 1")


@mutant("unverified path bypasses straight to Person Get", "G4")
def m8(wf):
    wf["connections"]["IF Member Verified"]["main"][1] = [
        {"node": "Person Get", "type": "main", "index": 0}]


@mutant("IF URL Found false branch never reaches the fallback (feature inert)", "G3")
def m9(wf):
    wf["connections"]["IF URL Found"]["main"][1] = [
        {"node": "Person Create", "type": "main", "index": 0}]


@mutant("PID From Member dead-ends (resolution silently dropped)", "G4")
def m10(wf):
    wf["connections"]["PID From Member"]["main"][0] = []


@mutant("a pre-existing node is mutated (frozen-workflow guard)", "G6")
def m11(wf):
    node(wf, "Person Search URL")["parameters"]["queryParameters"]["parameters"][0]["value"] = "=x"


@mutant("the existing FOUND path is re-pointed", "G5")
def m12(wf):
    wf["connections"]["IF URL Found"]["main"][0] = [
        {"node": "Person Search Member", "type": "main", "index": 0}]


@mutant("search by name instead of custom_fields (Make's key)", "G9")
def m13(wf):
    qp(wf, "Person Search Member", "fields")["value"] = "name"


@mutant("exact_match off -> fuzzy person matching", "G9")
def m14(wf):
    qp(wf, "Person Search Member", "exact_match")["value"] = "false"


@mutant("credentials stripped from the new search node", "G8")
def m15(wf):
    node(wf, "Person Search Member")["credentials"] = {}


@mutant("only one branch patched (M7 reply left without the fallback)", "G2")
def m16(wf):
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "M7 IF Member Verified"]
    wf["connections"].pop("M7 IF Member Verified", None)


@mutant("verify true but pid null (verified-but-unresolvable)", "V11")
def m17(wf):
    a = pid_asg(wf, "PID From Member")
    a["value"] = "={{ null }}"


def main():
    orig = TARGET.read_text(encoding="utf-8")
    canonical = json.dumps(json.loads(orig), ensure_ascii=False, indent=2)
    caught, escaped, notapplied = 0, [], []
    try:
        for label, expect, fn in MUTANTS:
            wf = json.loads(orig)
            fn(wf)
            mutated = json.dumps(wf, ensure_ascii=False, indent=2)
            if mutated == canonical:
                notapplied.append(label)
                print(f"  NOT APPLIED  {label}")
                continue
            TARGET.write_text(mutated + "\n", encoding="utf-8")
            r = subprocess.run(["node", str(TESTS)], capture_output=True, text=True)
            out = r.stdout + r.stderr
            if r.returncode == 0:
                escaped.append(f"{label} (expected {expect})")
                print(f"  ESCAPED  {label}")
            else:
                caught += 1
                mark = "" if expect in out else f"   (caught, but not by {expect})"
                print(f"  caught   {label}{mark}")
    finally:
        TARGET.write_text(orig, encoding="utf-8")
    print(f"\n{caught}/{len(MUTANTS)} mutants caught")
    if notapplied:
        print("MUTANTS THAT DID NOT APPLY (the harness lied):")
        for m in notapplied:
            print("  " + m)
    if escaped:
        print("HOLES:")
        for e in escaped:
            print("  " + e)
    if escaped or notapplied:
        sys.exit(1)


if __name__ == "__main__":
    main()
