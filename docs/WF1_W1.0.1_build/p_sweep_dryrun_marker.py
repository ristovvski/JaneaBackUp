#!/usr/bin/env python3
"""PRE-FIRE, item 2 of Nik's envelope: a dev summary must announce itself as a dry run.

On 2026-09-08 a MODE="dev" run posted `DNC -> Pipedrive: chunk 10/12 done · 250 processed
(224 labels, 26 field-only) · 330 remaining · 0 errors` to #gtm-telemetry having written NOTHING.
Every line is prefixed, not only the first: Slack truncates, and people quote single lines out of a
message.

SECOND CHANGE, and I am flagging it because it was not in the envelope: `PD Label Union` derives the
lead's new label set from `resp.data.label_ids` and falls back to `[]` when that is not an array. If
a `/v1/leads/{id}` GET ever answers 200 with a body we do not recognise, that fallback PATCHes
`label_ids = [dnc]` and WIPES every existing label - on 224 real leads, first time this node has
ever run live, in an estate that spent 24 days with four Zaps quietly stripping `Responded`. So the
node now distinguishes the two cases it was conflating:

  success + data present + no label_ids  -> genuinely unlabelled, union is [dnc]   (unchanged)
  anything else                          -> THROW rather than write a label set derived from nothing

Throwing aborts the run. That is the intended trade: rows already written keep their Mark Done, and
a systemic API-shape change stops the sweep instead of erasing labels. `PD Get Lead For Labels`
already routes genuine failures to its error output, so only a 200-with-strange-body reaches here.
"""
import argparse
import copy
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
SWEEP = "8qVXtI2ez5o6a9hc"

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
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:200]))
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


def code_only(js):
    out = []
    for line in js.splitlines():
        if line.strip().startswith("//"):
            continue
        out.append(re.sub(r"//.*$", "", line))
    return "\n".join(out)


wf = n8n("/api/v1/workflows/%s" % SWEEP)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}

# ------------------------------------------------------------------ A: DRY RUN marker
cs = N["Combine Summaries"]["parameters"]["jsCode"]
if "DRY RUN" in cs:
    sys.exit("dry-run marker already present")
ANCHOR = "const targetChannel = isFinalChunk ? cfg.alert_channel : cfg.telemetry_channel;"
if ANCHOR not in cs:
    sys.exit("Combine Summaries anchor not found verbatim")
MARKER = """// DRY RUN MARKER. On 2026-09-08 a MODE="dev" run posted "chunk 10/12 done · 250 processed"
// to #gtm-telemetry having written nothing at all - a report claiming success for work that never
// happened, which is this estate's most expensive recurring failure. EVERY line is prefixed, not
// just the first: Slack truncates long messages and people quote single lines out of them.
const __live = String(cfg.MODE) === 'live';
if (!__live) lines = lines.map(l => 'DRY RUN \\u2014 ' + l);

const targetChannel = isFinalChunk ? cfg.alert_channel : cfg.telemetry_channel;"""
cs_new = cs.replace(ANCHOR, MARKER, 1)
cs_new = cs_new.replace("  slack_text: lines.join('\\n'), is_final_chunk: isFinalChunk,",
                        "  slack_text: lines.join('\\n'), is_final_chunk: isFinalChunk,\n"
                        "  mode: String(cfg.MODE), dry_run: !__live,", 1)
if "dry_run: !__live" not in cs_new:
    sys.exit("could not add mode/dry_run to the returned json - shape changed")
N["Combine Summaries"]["parameters"]["jsCode"] = cs_new

# ------------------------------------------------------------------ B: label-union shape guard
lu = N["PD Label Union"]["parameters"]["jsCode"]
OLD_LU = ("const existing = (resp && resp.data && Array.isArray(resp.data.label_ids)) "
          "? resp.data.label_ids : [];")
if OLD_LU not in lu:
    sys.exit("PD Label Union existing-labels line not found verbatim")
NEW_LU = """// SHAPE GUARD (2026-09-08, before this node's first live run). The old fallback treated an
// UNRECOGNISED response exactly like a lead with no labels, so a 200 with an unexpected body would
// PATCH label_ids = [dnc] and wipe every existing label - on 224 real leads, in an estate that
// spent 24 days with four Zaps quietly stripping `Responded`. Distinguish the two:
//   success + data present, no label_ids -> genuinely unlabelled, union is [dnc]   (unchanged)
//   anything else -> throw, rather than write a label set derived from nothing.
// Throwing stops the sweep; rows already written keep their Mark Done. Genuine read failures never
// reach here - `PD Get Lead For Labels` routes those to its error output.
if (!(resp && resp.success === true && resp.data && typeof resp.data === 'object')) {
  throw new Error('PD Label Union: unrecognised /v1/leads response, refusing to derive a label set '
    + 'from nothing (lead ' + String(upstream && upstream.lead_id) + ')');
}
const existing = Array.isArray(resp.data.label_ids) ? resp.data.label_ids : [];"""
N["PD Label Union"]["parameters"]["jsCode"] = lu.replace(OLD_LU, NEW_LU, 1)
LU_NEW = N["PD Label Union"]["parameters"]["jsCode"]

# ------------------------------------------------------------------ statics
print("--- statics ---")
ok = True


def run(js, harness, pick="OUT"):
    src = harness + "\nlet __err = null; let OUT = null;\ntry { OUT = (() => {\n" + js \
        + "\n})(); } catch (e) { __err = String(e.message || e); }\n" \
          "console.log(JSON.stringify({ out: " + pick + ", err: __err }));\n"
    tmp = os.path.join(HERE, "_dr.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    os.remove(tmp)
    if p.returncode != 0:
        return None, (p.stderr or "").strip()[:300]
    d = json.loads(p.stdout.strip().splitlines()[-1])
    return d, None


PD = {"eligible": 580, "chunk_processed": 250, "remaining_after_chunk": 330,
      "with_open_lead": 224, "without_open_lead": 26}
PD_FINAL = {"eligible": 80, "chunk_processed": 80, "remaining_after_chunk": 0,
            "with_open_lead": 70, "without_open_lead": 10}
SL = {"eligible": 1548, "resolved_pending_action": 874, "already_unsubscribed": 46,
      "not_found": 628}
HR = {"eligible": 32425, "note": "PARKED"}


def cs_harness(mode, pd):
    cfg = {"MODE": mode, "pd_chunk_size": 250, "alert_channel": "C0B8GCVNR5W",
           "telemetry_channel": "C0BQM1X9ZUY"}
    return ("const PD=%s, SL=%s, HR=%s, CFG=%s;\n"
            "const CAND = new Array(2847).fill({});\n"
            "const SD = {};\n"
            "const $getWorkflowStaticData = () => SD;\n"
            "const $ = (n) => ({ first: () => ({ json: n==='PD Aggregate'?PD : n==='SL Aggregate'?SL"
            " : n==='HR Count Pending'?HR : n==='CONFIG'?CFG"
            " : n==='PD Count Write Errors'? (()=>{throw new Error('no errors node')})() : {} }),\n"
            "   all: () => n==='PD Get Candidates' ? CAND : [] });\n"
            % (json.dumps(pd), json.dumps(SL), json.dumps(HR), json.dumps(cfg)))


def lu_harness(resp, lead_id="L1"):
    return ("const RESP=%s;\n"
            "const $json = RESP;\n"
            "const UP = {identity_key:'k1', lead_id:'%s', projections_state:'{}'};\n"
            "const $ = (n) => ({ item: { json: n==='PD Split Rows'?UP:{} },\n"
            "  first: () => ({ json: n==='CONFIG'?{pd_label_dnc:'DNC-LABEL'}:{} }) });\n"
            % (json.dumps(resp), lead_id))


def lines_of(d):
    return (((d or {}).get("out") or [{}])[0].get("json") or {}).get("slack_text", "").split("\n")


# A1 dev, mid-sweep
d, err = run(cs_new, cs_harness("dev", PD))
ls = lines_of(d)
good = bool(ls) and all(l.startswith("DRY RUN — ") for l in ls) and len(ls) >= 2
print("  [%s] %-52s %d line(s), all prefixed=%s" % ("ok " if good else "FAIL",
                                                    "dev mid-sweep summary", len(ls), good))
if not good:
    print("        %s" % json.dumps(ls)[:300])
ok = ok and good

# A2 dev, FINAL chunk (more lines, incl. Total: and HeyReach)
d, err = run(cs_new, cs_harness("dev", PD_FINAL))
ls = lines_of(d)
good = len(ls) >= 4 and all(l.startswith("DRY RUN — ") for l in ls)
print("  [%s] %-52s %d line(s), all prefixed=%s" % ("ok " if good else "FAIL",
                                                    "dev FINAL-chunk summary", len(ls), good))
ok = ok and good

# A3 live: no prefix anywhere
d, err = run(cs_new, cs_harness("live", PD))
ls = lines_of(d)
j = (((d or {}).get("out") or [{}])[0].get("json") or {})
good = ls and not any("DRY RUN" in l for l in ls) and j.get("dry_run") is False \
    and j.get("mode") == "live"
print("  [%s] %-52s dry_run=%s mode=%s" % ("ok " if good else "FAIL",
                                           "live summary carries no marker",
                                           j.get("dry_run"), j.get("mode")))
ok = ok and good

# A4 non-vacuity: the OLD code in dev mode prefixes nothing
d, err = run(cs, cs_harness("dev", PD))
ls = lines_of(d)
good = ls and not any("DRY RUN" in l for l in ls)
print("  [%s] %-52s (proves the fix changed behaviour)" % ("ok " if good else "FAIL",
                                                           "non-vacuity: old code in dev"))
ok = ok and good

# B1 union preserves existing labels
d, err = run(LU_NEW, lu_harness({"success": True, "data": {"label_ids": ["A", "B"]}}))
got = ((d or {}).get("out") or {}).get("json") or {}
good = got.get("label_ids") == ["A", "B", "DNC-LABEL"]
print("  [%s] %-52s %s" % ("ok " if good else "FAIL", "label union preserves existing",
                           got.get("label_ids")))
ok = ok and good

# B2 genuinely unlabelled lead
d, err = run(LU_NEW, lu_harness({"success": True, "data": {"id": "L1"}}))
got = ((d or {}).get("out") or {}).get("json") or {}
good = got.get("label_ids") == ["DNC-LABEL"] and not (d or {}).get("err")
print("  [%s] %-52s %s" % ("ok " if good else "FAIL", "unlabelled lead -> [dnc], no throw",
                           got.get("label_ids")))
ok = ok and good

# B3 already labelled DNC -> no duplicate
d, err = run(LU_NEW, lu_harness({"success": True, "data": {"label_ids": ["DNC-LABEL", "X"]}}))
got = ((d or {}).get("out") or {}).get("json") or {}
good = got.get("label_ids") == ["DNC-LABEL", "X"]
print("  [%s] %-52s %s" % ("ok " if good else "FAIL", "dnc already present -> unchanged",
                           got.get("label_ids")))
ok = ok and good

# B4 unrecognised body THROWS instead of wiping
for label, resp in (("success:false", {"success": False, "data": {"label_ids": ["A"]}}),
                    ("no data key", {"success": True}),
                    ("empty body", {})):
    d, err = run(LU_NEW, lu_harness(resp))
    threw = bool((d or {}).get("err")) and "unrecognised" in ((d or {}).get("err") or "")
    print("  [%s] %-52s %s" % ("ok " if threw else "FAIL",
                               "unrecognised response (%s) throws" % label,
                               ((d or {}).get("err") or "no throw")[:60]))
    ok = ok and threw

# B5 non-vacuity: the OLD union code WIPES on the same unrecognised body
d, err = run(lu, lu_harness({"success": True}))
got = ((d or {}).get("out") or {}).get("json") or {}
wiped = got.get("label_ids") == ["DNC-LABEL"] and not (d or {}).get("err")
print("  [%s] %-52s old code returns %s (a wipe)" % ("ok " if wiped else "FAIL",
                                                     "non-vacuity: old union on a bad body",
                                                     got.get("label_ids")))
ok = ok and wiped

if not ok:
    print("\nRED - nothing deployed.")
    sys.exit(1)
print("\nall statics pass (11)")
if not a.deploy:
    print("--deploy not given: NOTHING WRITTEN.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "sweep_backup_before_dryrun_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("backup: sweep_backup_before_dryrun_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)
n8n("/api/v1/workflows/%s" % SWEEP, "PUT", put_body(wf))
after = n8n("/api/v1/workflows/%s" % SWEEP)
AN = {n["name"]: n for n in after["nodes"]}
problems = []
if "DRY RUN" not in code_only(AN["Combine Summaries"]["parameters"]["jsCode"]):
    problems.append("dry-run marker not live")
if "unrecognised" not in code_only(AN["PD Label Union"]["parameters"]["jsCode"]):
    problems.append("label-union guard not live")
if len(after["nodes"]) != len(ORIG["nodes"]):
    problems.append("node count changed")
if not after.get("active"):
    problems.append("SWEEP IS INACTIVE after the PUT")
cfg = next(n for n in after["nodes"] if n["name"] == "CONFIG")
vals = {a["name"]: a["value"] for a in
        ((cfg["parameters"].get("assignments") or {}).get("assignments") or [])}
print("\nlive verification: %s" % ("CLEAN" if not problems else "PROBLEMS"))
for p in problems:
    print("  -", p)
print("  sweep versionId=%s active=%s nodes=%d" % (after.get("versionId"), after.get("active"),
                                                   len(after["nodes"])))
print("  CONFIG still MODE=%s FIRE_PIPEDRIVE=%s FIRE_SMARTLEAD=%s" % (
    vals.get("MODE"), vals.get("FIRE_PIPEDRIVE"), vals.get("FIRE_SMARTLEAD")))
sys.exit(1 if problems else 0)
