#!/usr/bin/env python3
"""P0-2 permanent fix - port WF-2S onto `leads-statistics` `history[] type=SENT`.

THE BUG: `/campaigns/{id}/statistics` returns the OLDEST rows with no ordering control and caps
around 500. WF-2S therefore stopped seeing new sends once a campaign passed 500 rows - 817 SENT
rows never seen, 242 of them yesterday alone, while it reported "idle".

THE FIX IS A PORT, NOT AN INVENTION. WF-2R already polls `leads-statistics` in production with:
  * one campaign per cycle (pagination emits one item per PAGE, so multi-campaign index attribution
    is impossible - this is why `Carry Campaign`'s zip must go)
  * a resume cursor so an oversized campaign's walk completes across cycles
  * hasMore-driven pagination with a page cap
  * claim-after-success, unchanged here

Node NAMES are preserved exactly so no connection surgery is needed on a live workflow.
"""
import argparse, json, os, ssl, subprocess, sys, urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
WF2S = "6Y92ryBwYoy6z0Jx"

PICK_ONE = r"""
// PORTED FROM WF-2R. One campaign per cycle: n8n pagination emits one item per PAGE, so the old
// index-zip against a multi-campaign fan-out cannot work. Resume takes priority over rotation so an
// oversized campaign's walk always completes.
const rows = $input.all().map(i => i.json)
  .flatMap(j => Array.isArray(j) ? j : (Array.isArray(j.data) ? j.data : [j]));
const CFG = $('CONFIG').first().json;
const allow = (CFG.campaign_allowlist ?? []).map(String);
const sd = $getWorkflowStaticData('global');
if (!rows.length) {
  throw new Error('WF-2S: /campaigns returned nothing parseable - refusing to report "idle"');
}
const live = rows
  .filter(c => !['ARCHIVED', 'DRAFTED'].includes(String(c.status ?? '').toUpperCase()))
  .filter(c => !allow.length || allow.includes(String(c.id)));
const byId = (a, b) => String(a.id).localeCompare(String(b.id));
const isActive = (c) => String(c.status ?? '').toUpperCase() === 'ACTIVE';
const ageCut = Date.now() - Number(CFG.cold_max_age_days ?? 180) * 86400000;
const hot = live.filter(isActive).sort(byId);
const coldAll = live.filter(c => !isActive(c));
const cold = coldAll.filter(c => {
  const cr = Date.parse(c.created_at ?? '');
  return Number.isFinite(cr) ? cr >= ageCut : true;
}).sort(byId);
const excluded = coldAll.length - cold.length;
if (!hot.length && !cold.length) {
  return [{ json: { __none: true, __scanned: rows.length, __hot: 0, __cold: 0,
                    __excluded: excluded } }];
}
const ratio = Math.max(1, Number(CFG.hot_cycles_per_cold) || 3);
const resume = sd.__resume_sent || null;
let c = null, ringName = null, startOffset = 0, resumeRound = 0;
if (resume && resume.campaign_id) {
  const still = live.find(x => String(x.id) === String(resume.campaign_id));
  if (still) {
    c = still; ringName = 'resume';
    startOffset = Number(resume.next_offset) || 0;
    resumeRound = Number(resume.round) || 1;
  } else { sd.__resume_sent = null; }
}
if (!c) {
  const tick = Number(sd.__tick_sent ?? 0);
  sd.__tick_sent = tick + 1;
  const wantCold = (tick % (ratio + 1)) === ratio;
  const ring = (wantCold && cold.length) ? cold : (hot.length ? hot : cold);
  ringName = ring === cold ? 'cold' : 'hot';
  const curKey = ringName === 'cold' ? '__rr_cold_sent' : '__rr_hot_sent';
  const cursor = Number(sd[curKey] ?? 0) % ring.length;
  c = ring[cursor];
  sd[curKey] = (cursor + 1) % ring.length;
}
const cycleMin = 15;
const hotSweepH = hot.length ? hot.length * ((ratio + 1) / ratio) * cycleMin / 60 : 0;
const coldSweepH = cold.length ? cold.length * (ratio + 1) * cycleMin / 60 : 0;
const lookbackH = Number(CFG.lookback_minutes) / 60;
return [{ json: { campaign_id: c.id, campaign_name: c.name,
  campaign_status: String(c.status ?? '').toUpperCase(),
  start_offset: startOffset, resume_round: resumeRound,
  __scanned: rows.length, __ring: ringName, __hot: hot.length, __cold: cold.length,
  __excluded: excluded, __hot_sweep_h: Math.round(hotSweepH * 10) / 10,
  __cold_sweep_h: Math.round(coldSweepH * 10) / 10,
  __sweep_overrun: (hotSweepH > lookbackH) || (coldSweepH > lookbackH), __none: false } }];
"""

CARRY = r"""
// Single campaign per cycle now, so there is nothing to zip. The old positional attribution
// against a multi-campaign fan-out is gone with the endpoint that required it.
const camp = $('Pick Active').first().json;
return $input.all().map(it => ({ json: { ...(it.json || {}),
  __campaign_id: camp.campaign_id, __campaign_name: camp.campaign_name,
  __campaign_status: camp.campaign_status } }));
"""

FIND_NEW = r"""
const CFG = $('CONFIG').first().json;
const sd = $getWorkflowStaticData('global');
// claim-after-success preserved verbatim: READ here, WRITTEN only in Summary for accepted replays.
const seen = sd.__sent_seen_v2 = sd.__sent_seen_v2 || {};
const camp = $('Pick Active').first().json;
const cutoff = Date.now() - Number(CFG.lookback_minutes) * 60000;
const pages = $input.all().map(i => i.json || {});
const lastPage = pages.length ? pages[pages.length - 1] : {};
const truncated = lastPage.hasMore === true;
const startOffset = Number(camp.start_offset) || 0;
const pageLimit = Number(CFG.page_limit ?? 100);
const scannedTo = startOffset + pages.length * pageLimit;
const round = Number(camp.resume_round) || 0;
sd.__resume_sent = truncated
  ? { campaign_id: camp.campaign_id, campaign_name: camp.campaign_name,
      next_offset: scannedTo, round: round + 1 }
  : null;
const stuck = truncated && (round + 1) > (Number(CFG.max_resume_rounds) || 5);

const out = [];
let leads = 0, sents = 0, stale = 0, already = 0;
for (const page of pages) {
  for (const row of (page.data ?? [])) {
    leads++;
    for (const h of (row.history ?? [])) {
      if (String(h.type ?? '').toUpperCase() !== 'SENT') continue;
      sents++;
      const t = Date.parse(h.time || 0);
      if (!Number.isFinite(t) || t < cutoff) { stale++; continue; }
      // stats_id identifies the SENT step uniquely; fall back to the triple when absent
      const key = h.stats_id
        ? String(h.stats_id)
        : ('T|' + camp.campaign_id + '|' + row.lead_id + '|' + h.time);
      if (seen[key]) { already++; continue; }
      out.push({ campaign_id: camp.campaign_id, campaign_name: camp.campaign_name,
                 campaign_status: camp.campaign_status,
                 stats_id: h.stats_id ?? null, lead_id: row.lead_id,
                 lead_email: row.to, sender_inbox: row.from ?? null,
                 email_lead_map_id: row.email_lead_map_id ?? null,
                 sequence_number: h.email_seq_number ?? null,
                 sent_time: h.time, email_subject: h.subject ?? null, __key: key });
    }
  }
}
out.sort((a, b) => String(a.sent_time).localeCompare(String(b.sent_time)));
const cap = Math.max(1, Number(CFG.max_per_run) || 20);
const dropped = Math.max(0, out.length - cap);
const batch = out.slice(0, cap);
const meta = { __campaign_id: camp.campaign_id, __campaign_name: camp.campaign_name,
               __pages: pages.length, __truncated: truncated, __resuming: truncated,
               __stuck: stuck, __start_offset: startOffset, __scanned_to: scannedTo,
               __resume_round: round + (truncated ? 1 : 0),
               __leads: leads, __sents_seen: sents, __stale: stale, __already: already,
               __dropped: dropped, __considered: sents,
               __sweep_overrun: camp.__sweep_overrun === true };
if (!batch.length) return [{ json: { __idle: true, ...meta } }];
return batch.map((b, i) => ({ json: { ...b, ...meta, __batch: batch.length, __first: i === 0 } }));
"""


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

# ---------------- statics: execute Find New Sends against a REAL leads-statistics shape
FIXTURE = {
    "hasMore": False, "data": [
        {"lead_id": 111, "to": "pii-22fdb3ff@example.invalid", "from": "pii-6f267dd7@example.invalid", "email_lead_map_id": 9,
         "history": [
             {"type": "SENT", "time": "2026-08-11T06:00:00.000+00:00", "stats_id": "S1",
              "subject": "Hi", "email_seq_number": "1"},
             {"type": "REPLY", "time": "2026-08-11T06:05:00.000+00:00", "stats_id": "S1"},
             {"type": "SENT", "time": "2020-01-01T00:00:00.000+00:00", "stats_id": "OLD"}]},
        {"lead_id": 222, "to": "pii-7ea89e72@example.invalid", "from": "pii-6f267dd7@example.invalid",
         "history": [{"type": "SENT", "time": "2026-08-11T06:10:00.000+00:00", "stats_id": "S2"}]},
    ]}
tmp = os.path.join(HERE, "_p05check.js")
tests = [
    ("extracts SENT only, skips REPLY and stale", {}, 2),
    ("already-claimed SENT is skipped", {"__sent_seen_v2": {"S1": "x"}}, 1),
]
for label, statics, want in tests:
    js = f"""
const __sd = {json.dumps(statics)};
const $getWorkflowStaticData = () => __sd;
const $ = (nm) => ({{ first: () => ({{ json: nm === 'CONFIG'
  ? {{ lookback_minutes: 180, page_limit: 100, max_per_run: 20, max_resume_rounds: 5 }}
  : {{ campaign_id: 3686187, campaign_name: 'C', campaign_status: 'ACTIVE',
       start_offset: 0, resume_round: 0 }} }}) }});
const $input = {{ all: () => [{{ json: {json.dumps(FIXTURE)} }}] }};
const __out = (() => {{{FIND_NEW}}})();
const real = __out.filter(o => !o.json.__idle);
console.log(JSON.stringify({{ n: real.length,
  keys: real.map(o => o.json.__key), truncated: __out[0].json.__truncated }}));
"""
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    p = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print(f"  [FAIL] {label}: {(p.stderr or '').strip()[-200:]}")
        os.remove(tmp); sys.exit(1)
    got = json.loads(p.stdout.strip())
    ok = got["n"] == want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: found {got['n']} (want {want}) keys={got['keys']}")
    if not ok:
        os.remove(tmp); sys.exit(1)
os.remove(tmp)

wf = n8n(f"/api/v1/workflows/{WF2S}")
nodes = {n["name"]: n for n in wf["nodes"]}
cfg_node = nodes["CONFIG"]
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
cfg.update({"page_limit": 100, "max_pages_per_campaign": 35, "max_resume_rounds": 5,
            "hot_cycles_per_cold": 3, "cold_max_age_days": 180, "max_campaigns_per_cycle": 1})
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
nodes["Pick Active"]["parameters"]["jsCode"] = PICK_ONE.strip()
nodes["Carry Campaign"]["parameters"]["jsCode"] = CARRY.strip()
nodes["Find New Sends"]["parameters"]["jsCode"] = FIND_NEW.strip()
st = nodes["SL Statistics"]
st["parameters"]["url"] = ("={{ $('CONFIG').first().json.sl_api }}"
                           "{{ '/campaigns/' + ($json.campaign_id || 0) + '/leads-statistics' }}")
st["parameters"]["sendQuery"] = True
st["parameters"]["queryParameters"] = {"parameters": [
    {"name": "limit", "value": "={{ $('CONFIG').first().json.page_limit }}"},
    {"name": "offset", "value": "={{ $('Pick Active').first().json.start_offset || 0 }}"}]}
st["parameters"]["options"] = {"pagination": {"pagination": {
    "paginationMode": "updateAParameterInEachRequest",
    "parameters": {"parameters": [{"type": "qs", "name": "offset",
        "value": "={{ ($('Pick Active').first().json.start_offset || 0)"
                 " + $pageCount * $('CONFIG').first().json.page_limit }}"}]},
    "paginationCompleteWhen": "other",
    "completeExpression": "={{ $response.body.hasMore !== true }}",
    "limitPagesFetched": True,
    "maxRequests": "={{ $('CONFIG').first().json.max_pages_per_campaign }}"}}}

print("\nplanned: SL Statistics -> leads-statistics (paginated) · Pick Active -> one-per-cycle "
      "+ resume · Carry Campaign -> no zip · Find New Sends -> history[] type=SENT")
if not a.deploy:
    print("--deploy not given: nothing written.")
    sys.exit(0)

stamp = int(datetime.now(timezone.utc).timestamp())
open(os.path.join(HERE, f"wf2s_backup_before_leadstats_{stamp}.json"), "w",
     encoding="utf-8").write(json.dumps(n8n(f"/api/v1/workflows/{WF2S}"), indent=2,
                                        ensure_ascii=False))
was = wf.get("active")
if was:
    n8n(f"/api/v1/workflows/{WF2S}/deactivate", "POST", {})
d = stripped_keys(wf)
if d:
    print(f"stripping UI-only settings keys: {d}")
n8n(f"/api/v1/workflows/{WF2S}", "PUT", put_body(wf))
if was:
    n8n(f"/api/v1/workflows/{WF2S}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2S}")
an = {x["name"]: x for x in after["nodes"]}
acfg = json.loads(an["CONFIG"]["parameters"]["jsonOutput"])
problems = []
if "leads-statistics" not in json.dumps(an["SL Statistics"]["parameters"]):
    problems.append("SL Statistics not on leads-statistics")
if "__resume_sent" not in an["Pick Active"]["parameters"]["jsCode"]:
    problems.append("Pick Active not ported")
if "SENT" not in an["Find New Sends"]["parameters"]["jsCode"]:
    problems.append("Find New Sends not ported")
if after.get("active") is not was:
    problems.append(f"active={after.get('active')}")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")
print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active={after.get('active')} versionId={after.get('versionId')} "
      f"nodes={len(after['nodes'])} max_per_run={acfg.get('max_per_run')} "
      f"pages={acfg.get('max_pages_per_campaign')}")
sys.exit(1 if problems else 0)
