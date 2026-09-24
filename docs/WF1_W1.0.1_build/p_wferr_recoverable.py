#!/usr/bin/env python3
"""WF-ERR IMPACT wording — 'LOST' is now wrong for the events we can actually recover.

The alert told the channel a reply was 'LOST - this event will not be delivered again' while WF-2R
replayed it within the same minute (2026-08-13, the forward crash). That string was written before
WF-2R and P0-1b existed. It is not cosmetic: IMPACT is what tells a human whether to go hand-repair
something, and crying LOST on a recoverable event trains people to ignore the word.

The truth is per EVENT TYPE, not per workflow:
  REPLIED -> WF-2R replays unclaimed replies every 15 min (P0-1b leaves the key unclaimed on crash)
  SENT    -> WF-2S re-claims on its next cycle
  anything else (bounce, unsubscribe) -> genuinely LOST; no reconciler covers it

Note the field values are 'REPLIED' / 'SENT' - Normalize's own vocabulary, NOT Smartlead's
EMAIL_REPLY / EMAIL_SENT. Verified against 40 retained executions before keying on it; a map keyed
on the provider's names would have silently fallen through to the blanket LOST.
"""
import argparse, copy, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WFERR = "BbrXPABgOaaTJjD6"


def n8n(path, method="GET", body=None, attempt=0):
    import time
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=240, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and attempt < 6:
            time.sleep(10)
            return n8n(path, method, body, attempt + 1)
        raise SystemExit(f"n8n {method} {path} FAILED: HTTP {e.code} {e.read()[:200]}")
    except Exception:
        if attempt < 4:
            time.sleep(8)
            return n8n(path, method, body, attempt + 1)
        raise


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WFERR}")
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

# ---- 1. CONFIG: per-event verdicts for WF-2
cfg_raw = N["CONFIG"]["parameters"]["jsonOutput"]
cfg = json.loads(cfg_raw)
src = cfg["sources"]["jp7rum9Z0YDJkQWv"]
src["retry"] = ("WF-2 answers 200 before processing, so Smartlead will NOT retry - recovery is "
                "ours, and it depends on the event type")
src["verdict"] = ("LOST - no reconciler covers this event type, so it will not be delivered again")
src["verdicts"] = {
    "REPLIED": ("RECOVERABLE - P0-1b claims the key only after success, so WF-2R replays this "
                "reply within ~15 min. Proven live 2026-08-13: the forward crash was replayed "
                "inside the same minute. Check WF-2R's next report before hand-repairing"),
    "SENT": ("RECOVERABLE - WF-2S marks sends seen only after a successful replay, so its next "
             "15-minute cycle re-claims this one"),
}
new_cfg = json.dumps(cfg, indent=2, ensure_ascii=False)

# ---- 2. Build Report: choose the verdict by event, fall back honestly when the event is unknown
js = N["Build Report"]["parameters"]["jsCode"]
OLD = """if (src) impact += '. ' + src.retry + ' -> ' + src.verdict;
else impact += '. Retry behaviour for this workflow is not documented in CONFIG';"""
NEW = """// Recoverability is a property of the EVENT TYPE, not of the workflow: WF-2R covers replies and
// WF-2S covers sends, but nothing covers bounces or unsubscribes. Saying 'LOST' about an event a
// reconciler is about to replay (which happened on 2026-08-13) teaches people to ignore the word.
// Normalize's vocabulary is 'REPLIED' / 'SENT', NOT Smartlead's EMAIL_REPLY / EMAIL_SENT.
if (src) {
  const evKey = String(event || '').toUpperCase();
  const byEvent = (src.verdicts || {})[evKey] || null;
  const verdict = byEvent
    ? byEvent
    : (evKey || !src.verdicts
        ? src.verdict
        : 'UNKNOWN - the event type could not be read, so recoverability is undetermined; '
          + 'check the WF-2R and WF-2S reports before assuming anything was lost');
  impact += '. ' + src.retry + ' -> ' + verdict;
} else {
  impact += '. Retry behaviour for this workflow is not documented in CONFIG';
}"""
if OLD not in js:
    sys.exit("Build Report verdict block not found verbatim - refusing to patch blind")
new_js = js.replace(OLD, NEW, 1)

# ---------------------------------------------------------------- statics
print("--- statics: execute Build Report and read the IMPACT line ---")
ok = True
CASES = [
    ("REPLIED (the 2026-08-13 case) - must NOT say it will not be delivered again",
     "REPLIED", "RECOVERABLE", False),
    ("SENT - WF-2S re-claims", "SENT", "RECOVERABLE", False),
    ("BOUNCED - genuinely lost, the word must still work", "BOUNCED", "LOST", True),
    ("event unreadable - must not claim LOST", None, "UNKNOWN", False),
]
for label, ev, want_sub, want_lost in CASES:
    nz = "null" if ev is None else json.dumps({"event": ev, "campaign_name": "AI4",
                                               "lead": {"email": "a@b.c"}})
    src_js = f"""
const CFG = {new_cfg};
const TRIG = {{ workflow: {{ id: 'jp7rum9Z0YDJkQWv', name: 'WF-2' }},
                execution: {{ id: '1', error: {{ message: 'boom',
                              node: {{ name: 'Body SL Forward Email' }} }} }} }};
const NZ = {nz};
const RD = {{ Normalize: [{{ data: {{ main: [[{{ json: NZ }}]] }} }}] }};
const $json = {{ data: {{ resultData: {{ runData: NZ === null ? {{}} : RD }} }} }};
const $ = (nm) => {{
  if (nm === 'CONFIG') return {{ first: () => ({{ json: CFG }}) }};
  if (nm === 'Error Trigger') return {{ first: () => ({{ json: TRIG }}) }};
  throw new Error('absent ' + nm);
}};
const OUT = (() => {{
{new_js}
}})();
console.log(JSON.stringify({{ impact: OUT[0].json.__impact }}));
"""
    tmp = os.path.join(HERE, "_wferr.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src_js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        print(f"  [FAIL] {label}\n         {(p.stderr or '').strip()[:300]}")
        ok = False
        continue
    imp = json.loads((p.stdout or "").strip().splitlines()[-1])["impact"]
    has_sub = want_sub in imp
    says_lost = "will not be delivered again" in imp
    good = has_sub and (says_lost is want_lost)
    ok = good and ok
    print(f"  [{'ok ' if good else 'FAIL'}] {label}")
    print(f"         {imp[-150:]}")

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, f"wferr_backup_{stamp}.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
N["CONFIG"]["parameters"]["jsonOutput"] = new_cfg
N["Build Report"]["parameters"]["jsCode"] = new_js
stripped_keys(wf)
n8n(f"/api/v1/workflows/{WFERR}", "PUT", put_body(wf))
after = n8n(f"/api/v1/workflows/{WFERR}")
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "verdicts" not in AN["CONFIG"]["parameters"]["jsonOutput"]:
    problems.append("CONFIG verdicts not live")
if "src.verdicts" not in AN["Build Report"]["parameters"]["jsCode"]:
    problems.append("Build Report selector not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for x in problems:
    print("  -", x)
print(f"  WF-ERR versionId={after.get('versionId')} active={after.get('active')} "
      f"nodes={len(after['nodes'])}")
