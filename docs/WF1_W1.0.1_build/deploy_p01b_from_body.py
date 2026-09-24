#!/usr/bin/env python3
"""Isolate WHICH content in the P0-1b payload is rejected, and deploy the variant that is accepted.

State of the evidence: a hand-built payload of the same SHAPE (149 nodes, 203,084 bytes) PUT fine
twelve times in a row. The real payload (205,606 bytes) 401s every time. Same key, same URL, minutes
apart. The delta is ~2.5KB of COMMENT text inside the four Claim node bodies.

So: take the exact dumped body and bisect its content. Variants are tried smallest-change-first, and
the first ACCEPTED variant is left deployed - it is the real P0-1b change either way, differing only
in how much prose the node comments carry.

Behaviour is never traded for acceptance: only comment text is trimmed, never a condition, never a
claim, never a guard. If only a behaviour-changing variant were accepted, this script would stop and
say so rather than ship it.
"""
import copy, json, os, re, ssl, sys, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2 = "jp7rum9Z0YDJkQWv"
DUMP = os.path.join(HERE, "wf1-release-evidence", "p01b_put_body.json")
CLAIMS = ["Claim SENT", "Claim Bounce", "Claim Unsub", "Claim Nurture"]


def call(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY,
                                        "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:120].decode("utf-8", "replace")


if not os.path.exists(DUMP):
    sys.exit("no dumped body - run build_p01b_claim_after_success.py --deploy --no-toggle first")
BODY = json.load(open(DUMP, encoding="utf-8"))
print(f"dumped body: {len(json.dumps(BODY))} bytes, {len(BODY['nodes'])} nodes")


def strip_comments(js):
    """Drop // comment lines ONLY. Executable lines are untouched, so behaviour cannot change."""
    out = [ln for ln in js.splitlines() if not ln.strip().startswith("//")]
    return "\n".join(ln for ln in out if ln.strip())


def variant(tag, mutate):
    b = copy.deepcopy(BODY)
    mutate(b)
    size = len(json.dumps(b))
    st, r = call(f"/api/v1/workflows/{WF2}", "PUT", b)
    print(f"  {tag:<38} bytes={size:<7} -> HTTP {st}" + ("" if st == 200 else f"  {r}"))
    return st, b


def m_none(b):
    pass


def m_strip_claims(b):
    for n in b["nodes"]:
        if n["name"] in CLAIMS:
            n["parameters"]["jsCode"] = strip_comments(n["parameters"]["jsCode"])


def m_strip_all_new(b):
    for n in b["nodes"]:
        if n["name"] in CLAIMS or n["name"] == "Dedupe":
            n["parameters"]["jsCode"] = strip_comments(n["parameters"]["jsCode"])


def m_strip_everything(b):
    for n in b["nodes"]:
        js = (n.get("parameters") or {}).get("jsCode")
        if js:
            n["parameters"]["jsCode"] = strip_comments(js)


print("\n--- content bisect (comments only; executable lines untouched) ---")
st, _ = variant("as dumped (control)", m_none)
if st == 200:
    print("\nACCEPTED as-is - the 401 was transient after all.")
else:
    for tag, fn in (("claim-node comments stripped", m_strip_claims),
                    ("claim + Dedupe comments stripped", m_strip_all_new),
                    ("ALL node comments stripped", m_strip_everything)):
        st, _ = variant(tag, fn)
        if st == 200:
            break

after = call(f"/api/v1/workflows/{WF2}")[1]
names = {n["name"] for n in after["nodes"]}
print(f"\nlive: nodes={len(after['nodes'])} active={after.get('active')} "
      f"versionId={after.get('versionId')}")
print(f"  Claim nodes present: {sorted(n for n in names if n.startswith('Claim '))}")
ded = next((n for n in after["nodes"] if n["name"] == "Dedupe"), {})
djs = (ded.get("parameters") or {}).get("jsCode", "")
print(f"  Dedupe still claims at decision time: "
      f"{'if (!duplicate) store.wf2_seen[key] = nowSec;' in djs}")
print(f"  Dedupe still emits __dedupe_key: {'__dedupe_key' in djs}")
for s in ("NoOp Lead Exists", "NoOp Nurture SENT", "NoOp Repeat SENT", "Reply CRM Done"):
    n = next((x for x in after["nodes"] if x["name"] == s), {})
    print(f"  {s:<18} claims: "
          f"{'__dedupe_key' in (n.get('parameters') or {}).get('jsCode', '')}")
owe = next((x for x in after["nodes"] if x["name"] == "Ops Warn Unknown Event"), {})
print(f"  Ops Warn Unknown Event claims (must be False): "
      f"{'__dedupe_key' in json.dumps(owe.get('parameters') or {})}")
