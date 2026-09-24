#!/usr/bin/env python3
"""WF-2R replay envelope carries no sl_lead_email -> every recovered reply classifies 'ambiguous'
-> the Ganga gate suppresses its team alert. Recovery stops meaning delivery.

Two of my own fixes interacting. P0-1b + WF-2R exist so a crashed reply is recovered; the Ganga gate
(deployed the same night) silences anything whose identity it cannot verify. The replay envelope
cannot carry identity, so it is silenced by construction.

WIRE EVIDENCE, not theory:
  exec 16278  WF-2R replay of Person-7267ff83's 'Interested' reply
              sl_lead_email ABSENT -> __reply_class='ambiguous' -> gate 'suppressed_ambiguous'
              alert ok=None, forward none, lead none. A real Interested reply, silent.
  4/4 retained replays lack sl_lead_email; 3/3 live arrivals carry it. Structural, not accidental.

THE FIX is one field. `Build REPLY Payload` already sets `to_email: row.lead_email` - it has the
lead's address in hand, because leads-statistics rows key on the lead. Note the replay envelope's
to_email means the LEAD, the inverse of the live webhook where to_email is whoever hit reply. So
sl_lead_email := the same value makes the envelope identity-complete and self-consistent:
classifier sees sl_lead_email == to_email -> 'lead' -> alerts normally.

KNOWN AND ACCEPTED LIMIT: a replay cannot detect third_party - the provider row records the lead,
not the human who typed. A replayed Ganga-type reply will alert naming the LEAD. That is the right
failure direction (names a real lead, vs. today's silence) and __identity_reconstructed marks it so
the observability pair can say so out loud.

Statics assert the OLD build's failure case, per protocol.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2R = "U8Bb7Pdq7S6nzYPa"
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

wf = n8n(f"/api/v1/workflows/{WF2R}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
js = N["Build REPLY Payload"]["parameters"]["jsCode"]

ANCHOR = "    to_email: row.lead_email,"
if ANCHOR not in js:
    sys.exit("anchor 'to_email: row.lead_email,' not found - refusing to patch blind")
if "sl_lead_email:" in js:
    print("sl_lead_email already present - nothing to add")
    sys.exit(0)

ADD = """    to_email: row.lead_email,
    // IDENTITY ON REPLAY. WF-2 Normalize keys lead.email off sl_lead_email (the Ganga fix); without
    // it the classifier hits its explicit 'ambiguous' branch and First Reply Gate suppresses the
    // team alert - so a RECOVERED reply arrived silently (exec 16278, a real 'Interested' reply).
    // leads-statistics rows key on the lead, so row.lead_email IS the campaign lead. Note this
    // envelope's to_email means the LEAD, inverse of the live webhook where it is whoever replied.
    // A replay cannot see a third-party sender - the provider row does not record one - so a
    // replayed third-party reply alerts naming the lead. Flagged, not hidden.
    sl_lead_email: row.lead_email,
    __identity_reconstructed: true,"""
new_js = js.replace(ANCHOR, ADD, 1)

# ---------------------------------------------------------------- statics
print("--- statics: run the DEPLOYED WF-2 Normalize against both envelopes ---")
wf2 = n8n(f"/api/v1/workflows/{WF2}")
nz_js = next(n for n in wf2["nodes"] if n["name"] == "Normalize")["parameters"]["jsCode"]
cfg_node = next((n for n in wf2["nodes"] if n["name"] == "CONFIG"), None)
CFGJS = "{ fields: {}, forward_inbox_map: {}, forward_owner_map: {}, forward_default: 'x@y.z' }"
if cfg_node and (cfg_node.get("parameters") or {}).get("jsCode"):
    CFGJS = None  # use the real one below


def envelope(**kw):
    e = {"event_type": "EMAIL_REPLY", "campaign_id": 3085711, "lead_id": "999",
         "to_email": "pii-eb7de9be@example.invalid", "to_name": "Person-7267ff83",
         "from_email": "pii-95534f2a@example.invalid", "reply_body": "sounds good",
         "reply_category": "Interested", "message_id": "M1", "stats_id": "S1",
         "sl_email_lead_map_id": "77", "event_timestamp": "2026-08-13T17:30:00Z"}
    e.update(kw)
    return e


CASES = [
    ("OLD replay envelope (no sl_lead_email) - MUST be ambiguous, i.e. the bug",
     envelope(__reconciled=True, __reconciled_by="WF-2R"), "ambiguous"),
    ("NEW replay envelope (sl_lead_email == to_email) - alerts as a lead",
     envelope(__reconciled=True, __reconciled_by="WF-2R",
              sl_lead_email="pii-eb7de9be@example.invalid",
              __identity_reconstructed=True), "lead"),
    ("live third_party (Ganga) - must STILL classify third_party, no regression",
     envelope(sl_lead_email="pii-eb7de9be@example.invalid",
              to_email="pii-10d2dcec@example.invalid", to_name="Person-36e26da4"), "third_party"),
    ("live alias (jfarrar -> joseph.farrar) - must STILL classify alias",
     envelope(sl_lead_email="pii-1011b46b@example.invalid", to_email="pii-e56d5459@example.invalid"), "alias"),
]

ok = True
for label, env, want in CASES:
    src = f"""
const CFG = {{ fields: {{}}, forward_inbox_map: {{}}, forward_owner_map: {{}},
               forward_default: 'x@y.z' }};
const ENV = {json.dumps(env)};
const $json = {{ body: ENV }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ item: {{ json: CFG }}, first: () => ({{ json: CFG }}) }};
  return {{ item: {{ json: {{ body: ENV }} }}, first: () => ({{ json: {{ body: ENV }} }}) }};
}};
const $getWorkflowStaticData = () => ({{ wf2_seen: {{}} }});
const items = [{{ json: {{ body: ENV }} }}];
const __out = (() => {{
{nz_js}
}})();
const j = Array.isArray(__out) ? __out[0].json : __out;
console.log(JSON.stringify({{ cls: j.__reply_class, from: j.__reply_from,
                              lead: (j.lead || {{}}).email }}));
"""
    tmp = os.path.join(HERE, "_nzcase.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}\n         {(p.stderr or '').strip()[-260:]}")
        ok = False
        continue
    got = json.loads(p.stdout.strip().splitlines()[-1])
    good = got["cls"] == want
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         class={got['cls']!r} (want {want!r})  lead.email={got['lead']!r}")

# the patched WF-2R node must still be valid JS and must emit the field
# the node runs once for all items: rows come from 'Find New Replies', $input is the lead lookup,
# zipped by index, and it emits { json: { __body: {...} } } - the envelope is NESTED under __body.
src = f"""
const CFG = {{ synthetic_event_type: 'EMAIL_REPLY', sl_inbox_base: 'https://x/' }};
const ROWS = [{{ campaign_id: 3085711, campaign_name: 'AI4', lead_id: '999',
                 lead_email: 'pii-eb7de9be@example.invalid', sender_inbox: 'pii-6b9f81bf@example.invalid',
                 stats_id: 'S1', message_id: 'M1', reply_time: '2026-08-13T17:30:00Z',
                 subject: 'Re: hi', email_body: 'sounds good', sequence_number: 1,
                 email_lead_map_id: '77', __key: 'K1' }}];
const LOOKUP = [{{ email: 'pii-eb7de9be@example.invalid', first_name: 'Andrea',
                   last_name: 'Tassistro', lead_campaign_data: [
                     {{ campaign_id: 3085711, lead_category_id: 1 }} ] }}];
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ first: () => ({{ json: CFG }}), item: {{ json: CFG }} }};
  if (nm === 'Find New Replies') return {{ all: () => ROWS.map(r => ({{ json: r }})) }};
  throw new Error('unexpected node ' + nm);
}};
const $input = {{ all: () => LOOKUP.map(l => ({{ json: l }})),
                  first: () => ({{ json: LOOKUP[0] }}) }};
const $getWorkflowStaticData = () => ({{}});
let out;
try {{ out = (() => {{
{new_js}
}})(); }} catch (e) {{ console.log(JSON.stringify({{ err: String(e.message) }})); out = null; }}
if (out) {{
  const b = ((out[0] || {{}}).json || {{}}).__body || {{}};
  console.log(JSON.stringify({{ sl: b.sl_lead_email, to: b.to_email,
                                rec: b.__identity_reconstructed, n: out.length }}));
}}
"""
tmp = os.path.join(HERE, "_wf2rcase.js")
with open(tmp, "w", encoding="utf-8") as f:
    f.write(src)
p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
os.remove(tmp)
line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else "{}"
got = json.loads(line)
if p.returncode != 0 or got.get("err"):
    print(f"  [FAIL] patched Build REPLY Payload: "
          f"{got.get('err') or (p.stderr or '').strip()[-220:]}")
    ok = False
else:
    good = got.get("sl") == got.get("to") == "pii-eb7de9be@example.invalid" and got.get("rec") is True
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] patched Build REPLY Payload emits "
          f"sl_lead_email={got.get('sl')!r} __identity_reconstructed={got.get('rec')!r}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (the OLD envelope reproduces the bug; the NEW one classifies as a lead)")

if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wf2r_backup_before_identity_{stamp}.json"), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["Build REPLY Payload"]["parameters"]["jsCode"] = new_js
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WF2R}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WF2R}")
fj = next(n for n in after["nodes"] if n["name"] == "Build REPLY Payload")["parameters"]["jsCode"]
problems = []
if "sl_lead_email: row.lead_email," not in fj:
    problems.append("sl_lead_email missing from the live node")
if "__identity_reconstructed: true," not in fj:
    problems.append("__identity_reconstructed missing")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for x in problems:
    print("  -", x)
print(f"  WF-2R versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
