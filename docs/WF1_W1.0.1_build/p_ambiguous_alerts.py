#!/usr/bin/env python3
"""AMBIGUOUS ALERTS, flagged 'identity unverified'. Silence reserved for CONFIRMED third_party.

Nik's ruling (2026-08-14, section 0): a missing identity field is an INTERNAL failure class, and an
internal failure must never eat a live Interested reply. Mine did - Person-7267ff83's, exec 16278.

Two nodes:
  First Reply Gate  - __suppress_class drops 'ambiguous'; emits __identity_unverified for consumers
  Body Reply Alert  - the alert says so in the body, so nobody reads it as a verified lead reply

Statics assert the OLD build's failure case: the pre-fix replay envelope (no sl_lead_email) run
through the DEPLOYED Normalize must classify ambiguous, and the patched gate must now ALERT on it
with the flag set - where today it returns should=false / suppressed_ambiguous.
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


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code} {e.read()[:200]}")


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF2}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

# ---------------------------------------------------------------- 1. the gate
g = N["First Reply Gate"]["parameters"]["jsCode"]
OLD_G = """// Third-party and AMBIGUOUS replies do not alert the team channel: a colleague on someone else's
// thread is not the lead speaking. Ambiguous fails QUIET on alerts (safe direction, 9b.0f) but is
// always recorded, so its volume stays visible instead of becoming a silent default."""
NEW_G = """// Third-party replies do not alert the team channel: a colleague on someone else's thread is not
// the lead speaking. AMBIGUOUS DOES ALERT (Nik, 2026-08-14, section 0). The earlier 'fail quiet'
// reading was wrong about which direction is safe: a missing identity field is an INTERNAL failure,
// and an internal failure must never eat a live reply. It ate one - Person-7267ff83's 'Interested'
// (exec 16278, a WF-2R replay whose envelope carried no sl_lead_email). Silence is now reserved for
// a CONFIRMED third party; an unverified identity alerts with the doubt stated in the body."""
if OLD_G not in g:
    sys.exit("gate comment block not found verbatim - refusing to patch blind")
g2 = g.replace(OLD_G, NEW_G, 1)

OLD_S = "const __suppress_class = (__rc === 'third_party' || __rc === 'ambiguous');"
NEW_S = ("const __suppress_class = (__rc === 'third_party');\n"
         "const __identity_unverified = (__rc === 'ambiguous');")
if OLD_S not in g2:
    sys.exit("__suppress_class line not found verbatim - refusing to patch blind")
g2 = g2.replace(OLD_S, NEW_S, 1)

OLD_R = "  __reply_class: __rc,"
NEW_R = "  __reply_class: __rc,\n  __identity_unverified: __identity_unverified,"
if OLD_R not in g2:
    sys.exit("__reply_class output line not found - refusing to patch blind")
g2 = g2.replace(OLD_R, NEW_R, 1)

# ---------------------------------------------------------------- 2. the alert body
b = N["Body Reply Alert"]["parameters"]["jsCode"]
OLD_H = """const __headline = '💬 ' + who + paren + ' · ' + esc(n.campaign_name)
  + ' · via ' + esc(n.sender_inbox) + ' — ' + link
  + ' · ✉️ ' + esc(n.lead.email);"""
NEW_H = """// Declared BEFORE the headline statement, not inside it. A previous patch of mine put const
// declarations inside an object literal and took the forward path down for a night.
const __idUnverified = (() => {
  try { return $('First Reply Gate').item.json.__identity_unverified === true; }
  catch (e) { return false; }
})();
const __headline = '💬 ' + who + paren + ' · ' + esc(n.campaign_name)
  + ' · via ' + esc(n.sender_inbox) + ' — ' + link
  + ' · ✉️ ' + esc(n.lead.email)
  + (__idUnverified
      ? '\\n⚠️ *identity unverified* — this reply arrived without a lead address, so it is keyed to '
        + 'the campaign lead above and the person who actually wrote may differ.'
      : '');"""
if OLD_H not in b:
    sys.exit("headline block not found verbatim - refusing to patch blind")
b2 = b.replace(OLD_H, NEW_H, 1)

# ---------------------------------------------------------------- statics
print("--- statics ---")
nz_js = N["Normalize"]["parameters"]["jsCode"]
ok = True


def run(src, tag):
    tmp = os.path.join(HERE, f"_{tag}.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        e = (p.stderr or "").strip()
        keep = os.path.join(HERE, f"_failed_{tag}.js")
        with open(keep, "w", encoding="utf-8") as f:
            f.write(src)
        return None, e[:400] + f"   [harness kept at {os.path.basename(keep)}]"
    return json.loads((p.stdout or "").strip().splitlines()[-1]), None


ENV_REPLAY = {"event_type": "EMAIL_REPLY", "campaign_id": 3085711, "lead_id": "999",
              "to_email": "pii-eb7de9be@example.invalid", "to_name": "Person-7267ff83",
              "from_email": "pii-6b9f81bf@example.invalid", "reply_body": "sounds good",
              "reply_category": "Interested", "message_id": "M1", "stats_id": "S1",
              "__reconciled": True, "__reconciled_by": "WF-2R",
              "event_timestamp": "2026-08-13T17:30:00Z"}
ENV_3P = dict(ENV_REPLAY)
ENV_3P.pop("__reconciled", None)
ENV_3P.update({"sl_lead_email": "pii-eb7de9be@example.invalid",
               "to_email": "pii-10d2dcec@example.invalid"})

NZ_HARNESS = """
const CFG = { fields: {}, forward_inbox_map: {}, forward_owner_map: {}, forward_default: 'x@y.z' };
const ENV = %s;
const $json = { body: ENV };
const $ = (nm) => (nm === 'CONFIG'
  ? { item: { json: CFG }, first: () => ({ json: CFG }) }
  : { item: { json: { body: ENV } }, first: () => ({ json: { body: ENV } }) });
const $getWorkflowStaticData = () => ({ wf2_seen: {} });
const items = [{ json: { body: ENV } }];
const NZOUT = (() => {
%s
})();
const NZ = Array.isArray(NZOUT) ? NZOUT[0].json : NZOUT;
"""

for label, env, want_cls, want_should, want_flag in (
        ("OLD replay envelope -> ambiguous, and it MUST now alert with the flag",
         ENV_REPLAY, "ambiguous", True, True),
        ("confirmed third_party -> still silent, no regression",
         ENV_3P, "third_party", False, False)):
    src = (NZ_HARNESS % (json.dumps(env), nz_js)) + f"""
const $json2 = {{ __dedupe_key: 'K1', __lead_id: null }};
// the gate node declares its OWN `const CFG`; a mock closing over the name `CFG` inside the IIFE
// resolves to that one and dies in its temporal dead zone. Bind the outer copy under a free name.
const GCFG = CFG;
const GATEOUT = (() => {{
  const $json = $json2;
  const $ = (nm) => (nm === 'Normalize' ? {{ item: {{ json: NZ }} }}
                     : {{ item: {{ json: GCFG }}, first: () => ({{ json: GCFG }}) }});
  const $getWorkflowStaticData = () => ({{}});
{g2}
}})();
const G = GATEOUT[0].json;
console.log(JSON.stringify({{ cls: NZ.__reply_class, should: G.__should_alert,
                              reason: G.__alert_reason, flag: G.__identity_unverified }}));
"""
    got, err = run(src, "gatecase")
    if err:
        print(f"  [FAIL] {label}\n         {err}")
        ok = False
        continue
    good = (got["cls"] == want_cls and got["should"] is want_should
            and got["flag"] is want_flag)
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         class={got['cls']!r} should_alert={got['should']} "
          f"reason={got['reason']!r} identity_unverified={got['flag']}")

# the alert body must render the flag, and must NOT render it when identity is fine
for flag, want_in in ((True, True), (False, False)):
    src = f"""
const CFG = {{ pipedrive_base: 'https://pd', sl_inbox_base: 'https://sl/', fields: {{}} }};
const NORM = {{ campaign_name: 'AI4', sender_inbox: 'pii-5c0f51ba@example.invalid',
  lead: {{ email: 'pii-eb7de9be@example.invalid', full_name: 'Person-7267ff83',
           title: 'CTO', company: 'Owkin' }},
  reply: {{ body: 'sounds good' }}, reply_category: 'Interested' }};
const $json = {{ __lead_id: null, __person_id: 69696 }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }} }};
  if (nm === 'Normalize') return {{ item: {{ json: NORM }} }};
  if (nm === 'First Reply Gate') return {{ item: {{ json: {{ __identity_unverified: {str(flag).lower()} }} }} }};
  throw new Error('absent ' + nm);
}};
const $getWorkflowStaticData = () => ({{}});
const OUT = (() => {{
{b2}
}})();
const j = Array.isArray(OUT) ? OUT[0].json : OUT;
const txt = String(j.alert_text || j.__headline || JSON.stringify(j));
console.log(JSON.stringify({{ has: txt.indexOf('identity unverified') !== -1,
                              len: txt.length }}));
"""
    got, err = run(src, "bodycase")
    if err:
        print(f"  [FAIL] alert body (flag={flag})\n         {err}")
        ok = False
        continue
    good = got["has"] is want_in
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] alert body flag={flag} -> "
          f"'identity unverified' present={got['has']} (want {want_in})")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2_backup_before_ambiguous_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["First Reply Gate"]["parameters"]["jsCode"] = g2
N["Body Reply Alert"]["parameters"]["jsCode"] = b2
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "const __suppress_class = (__rc === 'third_party');" not in \
        AN["First Reply Gate"]["parameters"]["jsCode"]:
    problems.append("gate suppress rule not live")
if "__identity_unverified: __identity_unverified," not in \
        AN["First Reply Gate"]["parameters"]["jsCode"]:
    problems.append("gate flag not emitted")
if "identity unverified" not in AN["Body Reply Alert"]["parameters"]["jsCode"]:
    problems.append("alert body flag not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for x in problems:
    print("  -", x)
print(f"  WF-2 versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
