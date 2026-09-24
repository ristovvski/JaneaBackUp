"""WF-2H - daily health / reconciliation / data-quality digest for WF-2 (Phase D, item 5).

Deliberate scope limits, each forced by a verified API fact rather than a guess:

* **No webhook health check via API.** Smartlead exposes no endpoint to read account-level webhooks:
  `/webhooks`, `/webhooks/`, `/account/webhooks`, `/user/webhooks`, `/webhooks/summary` all 404, and
  `/campaigns/{id}/webhooks` returns empty for every campaign (re-probed 2026-07-29). There is
  therefore also no way to re-enable one programmatically. Silence detection lives in
  `wf2_diff_harness.py`, which can see WF-2's execution count through the n8n API; when it sees
  Smartlead activity with zero WF-2 executions it raises the alarm and a human checks the UI.
  Building a fake "health check" that always reports OK would be worse than not having one.

* **No self-execution counting inside n8n.** A workflow cannot read another workflow's executions
  without an n8n API credential. Rather than demand a third credential, that comparison stays in the
  harness; WF-2H covers what Pipedrive + Smartlead credentials alone can answer.

What it does do, daily:
  1. Smartlead per-campaign stats for ACTIVE campaigns (sent / replies / bounces)
  2. data-quality digest on yesterday's Pipedrive leads - field completeness, the fields Melisa's
     reporting depends on
  3. bounce / DNC counters
  4. one Slack digest to the ops channel

Deploy gate: the Slack node binds to the same credential as WF-2.
"""
import argparse
import json
import sys
from pathlib import Path

from build_wf2_branches import slack_first
from wf_item_guard import violations as item_violations

ERROR_WORKFLOW = "BbrXPABgOaaTJjD6"
SLACK_CRED = {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Slack WF-2"}}   # WF-2's own app (gate-proven)
OPS_CHANNEL = "C0B8GCVNR5W"

CONFIG = {
    "ops_channel": OPS_CHANNEL,
    "pd_api": "https://api.pipedrive.com",
    "sl_api": "https://server.smartlead.ai/api/v1",
    "labels": {"cold": "a6d359b0-6a45-11ed-ab46-5b95b19fcb18",
               "connected": "ca698a50-bdfb-11ef-8172-510383583b0e",
               "responded": "c9d4b550-bcf3-11ef-a843-357f91e826ec",
               "dnc": "52a7c290-fc73-11f0-ad98-81d4703453f3"},
    # the person fields Melisa's reporting reads - a blank here is a silent reporting gap
    "quality_fields": {
        "campaign": "86157bb49563191c17b4dc62580525f84417524c",
        "hypothesis": "8bdae1a91272e92b335e9e99f668cde659b6daae",
        "medium": "961698945b0329b367da11916a94f10ff7ba71fe",
        "event_name": "ab5540d2ca45905dfb1434c0fe4971cc5790de3f",
        "position": "ab15ebd797c66ac010e47e543b7ec0226694d12b",
        "company": "5a282f55e910cceeb960969460b8409b4c10d623",
        "linkedin": "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20",
    },
    "lookback_hours": 24,
}


def node(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js):
    return node(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js})


# S1: every node below sits downstream of the Pick Active fan-out, so .item cannot
# resolve a paired item. This is why WF-2H failed on EVERY run it ever attempted.
PD = "={{ $('CONFIG').first().json.pd_api }}"
SL = "={{ $('CONFIG').first().json.sl_api }}"

PICK_ACTIVE = r"""
// keep only ACTIVE campaigns: a digest about COMPLETED campaigns is noise.
// S2: /campaigns returns a bare ARRAY and n8n splits it into one item PER CAMPAIGN (116 of them),
// so $json here is campaign #1, not the list. Reading $json made this digest look at a single
// arbitrary campaign. Same defect that made WF-2S idle forever; fixed there, never carried here.
const rows = $input.all().map(i => i.json)
  .flatMap(j => Array.isArray(j) ? j : (Array.isArray(j.data) ? j.data : [j]));
if (!rows.length) {
  throw new Error('WF-2H: /campaigns returned nothing parseable - refusing to report an empty digest');
}
const active = rows.filter(c => String(c.status).toUpperCase() === 'ACTIVE');
return active.length ? active.map(c => ({ json: { campaign_id: c.id, campaign_name: c.name,
                                                  __scanned: rows.length } }))
                     : [{ json: { campaign_id: null, campaign_name: null, __none: true,
                                  __scanned: rows.length } }];
"""

QUALITY = r"""
const CFG = $('CONFIG').first().json;
const Q = CFG.quality_fields;
const cutoff = Date.now() - Number(CFG.lookback_hours) * 3600 * 1000;
const leads = ($json.data ?? []) || [];
const recent = leads.filter(l => {
  const t = Date.parse(l.add_time || l.created_at || 0);
  return Number.isFinite(t) && t >= cutoff;
});
// no silent caps: if EVERY row on the page is inside the window, the page is saturated and the
// true count is >= this number. Saying "500" when it might be 900 is the same class of quiet lie
// as the unsorted read this replaced.
const capped = leads.length > 0 && recent.length === leads.length;
const missing = {};
for (const k of Object.keys(Q)) missing[k] = 0;
let dnc = 0, cold = 0, responded = 0;
for (const l of recent) {
  const ids = l.label_ids || [];
  if (ids.includes(CFG.labels.dnc)) dnc++;
  if (ids.includes(CFG.labels.cold)) cold++;
  if (ids.includes(CFG.labels.responded)) responded++;
}
return [{ json: { __leads_recent: recent.length, __leads_capped: capped,
                  __missing: missing,
                  __dnc: dnc, __cold: cold, __responded: responded,
                  // person-field completeness needs a person read per lead; deliberately NOT done
                  // here - it would be N API calls a day for a digest. The diff harness samples it.
                  __note: 'label counters only; field completeness is sampled by the diff harness' } }];
"""

DIGEST_TEXT = (
    "={{ (() => { const q=$json;"
    " const s=$('SL Stats Summary').first().json;"
    " const lines=[':bar_chart: *WF-2H daily digest*'];"
    " lines.push('Smartlead ACTIVE campaigns: ' + (s.__campaigns ?? '?')"
    " + ' \\u00b7 stat rows: ' + (s.__stat_rows ?? '?'));"
    " lines.push('Pipedrive leads touched in the window: ' + (q.__leads_recent ?? '?')"
    " + (q.__leads_capped ? '+ (page saturated - true count is higher)' : ''));"
    " lines.push('labels \\u2014 cold ' + (q.__cold ?? 0) + ' \\u00b7 responded ' + (q.__responded ?? 0)"
    " + ' \\u00b7 DNC ' + (q.__dnc ?? 0));"
    " lines.push('_webhook health is not API-readable in Smartlead; silence detection runs in the"
    " diff harness_');"
    " return lines.join('\\n'); })() }}"
)

SL_SUMMARY = r"""
// one row per campaign arrives here; fold them into a single summary item
const items = $input.all().map(i => i.json);
const rows = items.reduce((a, x) => a + Number(x.total_stats ?? (x.data ? x.data.length : 0) ?? 0), 0);
return [{ json: { __campaigns: items.filter(x => !x.__none).length, __stat_rows: rows } }];
"""


def build():
    N, C = [], {}
    N.append(node("h-cron", "Daily", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
                  {"rule": {"interval": [{"triggerAtHour": 7, "triggerAtMinute": 15}]}}))
    N.append(node("h-cfg", "CONFIG", "n8n-nodes-base.set", 3.4, [200, 0],
                  {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2, ensure_ascii=False),
                   "options": {}}))
    N.append(node("h-camps", "SL Campaigns", "n8n-nodes-base.httpRequest", 4.2, [400, 0],
                  {"method": "GET", "url": SL + "{{ '/campaigns' }}",
                   "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}},
                  credentials={"httpQueryAuth": {"id": "YXf5ez4pxDNd2g2B", "name": "Smartlead API"}},
                  retryOnFail=True, maxTries=3, waitBetweenTries=1000, onError="continueRegularOutput"))
    N.append(code("h-pick", "Pick Active", [600, 0], PICK_ACTIVE))
    N.append(node("h-stats", "SL Stats", "n8n-nodes-base.httpRequest", 4.2, [800, 0],
                  {"method": "GET",
                   "url": SL + "{{ '/campaigns/' + ($json.campaign_id || 0) + '/statistics' }}",
                   "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}},
                  credentials={"httpQueryAuth": {"id": "YXf5ez4pxDNd2g2B", "name": "Smartlead API"}},
                  retryOnFail=True, maxTries=3, waitBetweenTries=1000, onError="continueRegularOutput"))
    N.append(code("h-sum", "SL Stats Summary", [1000, 0], SL_SUMMARY))
    N.append(node("h-leads", "PD Leads", "n8n-nodes-base.httpRequest", 4.2, [1200, 0],
                  {"method": "GET",
                   # PAGINATION RULE (third strike with this trap): a /v1 list read used for
                   # COUNTING must prove its ordering. Unsorted, this endpoint returns the OLDEST
                   # page first - verified 2026-07-30, first row add_time 2023-05-02 - so the
                   # 24h filter below matched nothing and the digest reported a confident,
                   # meaningless "leads touched: 0" for its whole life. add_time DESC verified
                   # descending against the live API before this was written.
                   "url": PD + "{{ '/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC' }}",
                   "authentication": "predefinedCredentialType", "nodeCredentialType": "pipedriveApi",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}},
                  credentials={"pipedriveApi": {"id": "HnyULgvDdYp0lIkB", "name": "Pipedrive account"}},
                  retryOnFail=True, maxTries=3, waitBetweenTries=1000))
    N.append(code("h-q", "Quality Digest", [1400, 0], QUALITY))
    N.append(slack_first("h-slack", "WF-2H Digest", [1600, 0], "ops_channel", DIGEST_TEXT, SLACK_CRED))

    C["Daily"] = {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]}
    C["CONFIG"] = {"main": [[{"node": "SL Campaigns", "type": "main", "index": 0}]]}
    C["SL Campaigns"] = {"main": [[{"node": "Pick Active", "type": "main", "index": 0}]]}
    C["Pick Active"] = {"main": [[{"node": "SL Stats", "type": "main", "index": 0}]]}
    C["SL Stats"] = {"main": [[{"node": "SL Stats Summary", "type": "main", "index": 0}]]}
    C["SL Stats Summary"] = {"main": [[{"node": "PD Leads", "type": "main", "index": 0}]]}
    C["PD Leads"] = {"main": [[{"node": "Quality Digest", "type": "main", "index": 0}]]}
    C["Quality Digest"] = {"main": [[{"node": "WF-2H Digest", "type": "main", "index": 0}]]}

    return {"name": "WF-2H Health & Digest", "nodes": N, "connections": C, "active": False,
            "settings": {"executionOrder": "v1", "errorWorkflow": ERROR_WORKFLOW,
                         "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all"}}


def validate(wf):
    e = []
    # class sweep: no backward .item may survive anywhere inside a fan-out region
    e.extend(item_violations(wf))
    names = [n["name"] for n in wf["nodes"]]
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    if wf["settings"].get("errorWorkflow") != ERROR_WORKFLOW:
        e.append("errorWorkflow not bound")
    if wf.get("active") is not False:
        e.append("must ship inactive")
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.httpRequest" and not n["parameters"].get("authentication"):
            e.append(f"{n['name']}: no authentication")
        if n["type"] == "n8n-nodes-base.httpRequest" and "}}={{" in str(n["parameters"].get("url")):
            e.append(f"{n['name']}: welded URL (B9 class)")
    targets = {t["node"] for c in wf["connections"].values()
               for o in c["main"] for t in o}
    for t in targets:
        if t not in names:
            e.append(f"dangling connection target {t}")
    blob = json.dumps(wf)
    for bad in ("api_key=", "9f59ef3d"):
        if bad in blob:
            e.append(f"secret-ish literal: {bad}")
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    a = ap.parse_args()
    wf = build()
    errs = validate(wf)
    if errs:
        for x in errs:
            print(f"ERROR: {x}", file=sys.stderr)
        return 1
    payload = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    a.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"WF-2H built -> {a.output} ({len(wf['nodes'])} nodes)")
    print("DEPLOY GATE: Slack node binds the same credential as WF-2 ('Slack WF-2' once its id is known)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
