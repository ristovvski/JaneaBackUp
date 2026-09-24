#!/usr/bin/env python3
"""2 (second half) — the explicit-opt-out Responded gate, WF-2.

Melisa's ruling: a DNC/opt-out flag means WE do not COLD-CONTACT them. It never blocks replying when
someone writes to us first. After Friday's cleanup the DNC label means *explicit opt-out only* (it
used to mean "was in our campaigns", which is why Person-9979a87c carried it wrongly).

So the reply still alerts, and the reply activity is still written. What must NOT happen is the
pipeline quietly promoting an opted-out lead to `3. Responded` - that reads downstream as a live
warm lead and re-enters nurture. Instead the normal alert carries a "previously opted out" flag so
whoever picks it up has the context.

  ~ Body Lead Labels Union  drops `responded` from the target set when the lead already carries the
                            opt-out label; everything else unchanged (union still never removes)
  ~ Body Reply Alert        renders "previously opted out" when that applies

Note the direction: this SUPPRESSES A WRITE, not an alert. Alert gates fail open, write gates fail
closed (9b.0f) - and here the alert is exactly what we want to keep.
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
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
optout = (cfg.get("labels") or {}).get("dnc")
if not optout:
    sys.exit("CONFIG.labels.dnc absent - refusing to guess the opt-out label id")
print(f"opt-out label id (CONFIG.labels.dnc): {optout}")

blu = N["Body Lead Labels Union"]["parameters"]["jsCode"]
if "__opted_out" in blu:
    sys.exit("already gated")
ANCH = "const union = existing.slice();"
if ANCH not in blu:
    sys.exit("Body Lead Labels Union anchor missing")
GATE = """// EXPLICIT-OPT-OUT GATE (Melisa, 2026-08-18). An opt-out means we do not COLD-CONTACT them; it
// never blocks a reply they started. But promoting them to `3. Responded` would read downstream as
// a live warm lead and pull them back into nurture - so the label is withheld while the alert and
// the activity still happen. Keyed on the lead's EXISTING labels: after Friday's cleanup this label
// means explicit opt-out only (it used to mean "was in our campaigns", which is how Person-9979a87c
// carried it wrongly). Suppressing a WRITE, not an alert - see 9b.0f.
const __opted_out = Array.isArray(existing) && existing.includes(CFG.labels.dnc);
if (__opted_out) {
  const __i = target.indexOf(CFG.labels.responded);
  if (__i !== -1) target.splice(__i, 1);
}
"""
blu = blu.replace(ANCH, GATE + ANCH, 1)
OLDJ = "__skip: !changed || !_leadId, __label_union: union,"
if OLDJ not in blu:
    sys.exit("Body Lead Labels Union emit line not found verbatim")
blu = blu.replace(OLDJ, "__skip: !changed || !_leadId, __label_union: union,\n"
                        "    __opted_out, __responded_withheld: __opted_out,", 1)
N["Body Lead Labels Union"]["parameters"]["jsCode"] = blu

bra = N["Body Reply Alert"]["parameters"]["jsCode"]
if "previously opted out" in bra:
    sys.exit("alert flag already present")
AN2 = "const __idUnverified = (() => {"
if AN2 not in bra:
    sys.exit("Body Reply Alert anchor missing")
FLAG = """// Declared before the headline statement, never inside the object literal.
const __optedOut = (() => {
  try { return $('Body Lead Labels Union').item.json.__opted_out === true; }
  catch (e) { return false; }
})();
"""
bra = bra.replace(AN2, FLAG + AN2, 1)
OLDT = "  + (__idUnverified"
if OLDT not in bra:
    sys.exit("headline suffix anchor missing")
bra = bra.replace(OLDT,
                  "  + (__optedOut\n"
                  "      ? '\\n\\u26a0\\ufe0f *previously opted out* \\u2014 they contacted us, so "
                  "replying is fine; do NOT add them back to outbound. \\'3. Responded\\' was "
                  "withheld deliberately.'\n      : '')\n" + OLDT, 1)
N["Body Reply Alert"]["parameters"]["jsCode"] = bra

print("\n--- statics ---")
ok = True


def run(js, harness, pick):
    src = harness + "\nconst OUT = (() => {\n" + js + "\n})();\nconsole.log(JSON.stringify(" + pick + "));\n"
    tmp = os.path.join(HERE, "_oo.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


COLD = (cfg["labels"]["cold"])
CONN = (cfg["labels"]["connected"])
RESP = (cfg["labels"]["responded"])
BLU = N["Body Lead Labels Union"]["parameters"]["jsCode"]


def h_union(existing):
    return f"""
const CFG = {json.dumps(cfg)};
// `existing` is read via ctx('__lead_labels', ...) - NOT from a lead object. A harness that
// supplies data:[lead] silently yields existing=[] and every assertion becomes meaningless.
const $json = {{ __lead_id: 'L1', __lead_labels: {json.dumps(existing)} }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: {{ event: 'REPLIED', campaign_name: 'AI4',
      reply_category: null, lead: {{ email: 'a@b.c' }} }} }} }};
  return {{ item: {{ json: {{ __lead_id: 'L1', __lead_labels: {json.dumps(existing)} }} }} }};
}};
const $getWorkflowStaticData = () => ({{}});
"""


CASES = [
    ("opted-out lead replies -> responded WITHHELD, other labels still union",
     [COLD, CONN, optout], False),
    ("normal lead replies -> responded ADDED as before (no regression)",
     [COLD, CONN], True),
]
for label, existing, want_resp in CASES:
    got, err = run(BLU, h_union(existing), "{u: OUT[0].json.__label_union, oo: OUT[0].json.__opted_out}")
    if err:
        print(f"  [FAIL] {label}\n         {err}")
        ok = False
        continue
    u = got["u"] or []
    has = RESP in u
    good = has is want_resp and got["oo"] is (optout in existing)
    # union must never remove what was there
    kept = all(x in u for x in existing)
    good = good and kept
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         responded_present={has} (want {want_resp}) opted_out={got['oo']} "
          f"nothing_removed={kept} union={len(u)}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_optout_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "__opted_out" not in AN["Body Lead Labels Union"]["parameters"]["jsCode"]:
    problems.append("union gate not live")
if "previously opted out" not in AN["Body Reply Alert"]["parameters"]["jsCode"]:
    problems.append("alert flag not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  WF-2 versionId={after.get('versionId')} nodes={len(after['nodes'])}")
