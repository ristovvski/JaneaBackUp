"""WF-ERR v2 - actionable error reports.

v1 posted four bare lines: workflow, node, error message, execution URL. Reading it told you
something broke; it never told you whether anything was lost or what to do. Every triage started
from zero.

v2 answers the three questions a human actually has:

    WHAT   - plain language: which workflow, which branch/event, which node class
    IMPACT - what was and was not done: real writes completed before the failure (read from the
             failed execution's runData), whether the SOURCE will retry, and therefore whether data
             is lost, delayed, or safe
    ACTION - what to do, from a documented KNOWN-CLASSES dictionary in CONFIG

Design decisions worth stating:

* The Error Trigger payload carries workflow + execution METADATA only - no runData. So IMPACT is
  genuinely unknowable from the trigger alone. v2 fetches the failed execution through the n8n API
  (same read-only credential the WF-2S watchdog uses) to see which write nodes actually ran. If that
  fetch fails, the report degrades to metadata-only rather than inventing an impact line.

* UNKNOWN classes get an LLM hypothesis, clearly marked as a hypothesis. HARD GUARDRAIL: error
  reporting must never depend on the LLM being up, so the LLM node is continueRegularOutput and the
  compose step emits the plain report when no hypothesis came back.

* Burst suppression: the Lead List 400 lavina proved that N identical failures produce N identical
  messages and the channel becomes unreadable exactly when it matters most. One message per
  (workflow, node) per window; the next message after the window reports how many were suppressed.

* NO SECRETS, NO FULL PAYLOADS leave this workflow: the LLM sees node name, error text, event type
  and campaign name only. Enforced by a static.
"""
import argparse
import json
import sys
from pathlib import Path

from wf_item_guard import violations as item_violations

SLACK_CRED = {"slackApi": {"id": "Udq1K604RpJqg1cR", "name": "Slack account 3"}}
N8N_CRED = {"httpHeaderAuth": {"id": "3dbKbrfihcGrOJck", "name": "n8n API (WF-2S watchdog)"}}
LLM_CRED = {"openAiApi": {"id": "ltWhbdbiCcOBKnLn", "name": "OpenAI API"}}

CONFIG = {
    "ops_channel": "C0B8GCVNR5W",
    "n8n_api": "https://janea-systems-2025.app.n8n.cloud/api/v1",
    "burst_window_minutes": 15,
    "llm": {
        "base": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-5.2",
        "max_completion_tokens": 300,
    },
    # write nodes across all four workflows - presence in runData means the write really happened
    "write_nodes": [
        "Person Create", "Person Patch", "Org Create", "Lead Create", "Lead Labels Union",
        "SL Category", "SL Forward Email", "SL Unsubscribe", "Reply Activity", "Bounce Note",
        "U Lead DNC Label", "U SL Unsubscribe", "Replay Into WF-2",
    ],
    # retry semantics per source. This is the difference between "lost" and "it comes back".
    "sources": {
        "2jdjKM2NJr473GdA": {
            "label": "WF-1 HeyReach receiver",
            "retry": "HeyReach retries a failed webhook up to 5x over 24h",
            "verdict": "DELAYED - the event should come back on its own",
        },
        "jp7rum9Z0YDJkQWv": {
            "label": "WF-2 Smartlead receiver",
            "retry": "WF-2 answers 200 before processing, so Smartlead will NOT retry",
            "verdict": "LOST - this event will not be delivered again",
        },
        "6Y92ryBwYoy6z0Jx": {
            "label": "WF-2S SENT reconciler",
            "retry": "sends are marked seen only after a successful replay",
            "verdict": "SAFE - the next 15-minute cycle re-claims it",
        },
        "nK3yIOqRcBearV8s": {
            "label": "WF-2H health digest",
            "retry": "daily job, recomputed from scratch each run",
            "verdict": "DELAYED - nothing lost, the digest is just late",
        },
    },
    # documented classes, matched against error text and node name, in order
    "known_classes": [
        {"id": "paired_item",
         "match": "Paired item data",
         "what": "a node reached backward for an item that no longer has a pairing",
         "action": "Builder defect (S1 class). Run `python wf_item_guard.py` - it names the node. "
                   "Fix with .first() for singletons or .all()+index, then redeploy."},
        {"id": "oom",
         "match": "out-of-memory|did not finish",
         "what": "the n8n worker died mid-execution",
         "action": "Instance-level event, not a workflow defect. Check whether a burst of work "
                   "coincided (WF-2S scan size is the usual driver). The in-flight event may be "
                   "lost - see IMPACT."},
        {"id": "upstream_5xx",
         "match": "50[0-9]|ETIMEDOUT|ECONNRESET|socket hang up|EAI_AGAIN",
         "what": "an upstream API failed transiently",
         "action": "No action. Retries or the next cycle cover this. Only investigate if it "
                   "repeats across several windows."},
        {"id": "auth",
         "match": "401|403|Unauthorized|Forbidden|API key",
         "what": "a credential was rejected",
         "action": "Check the credential and any rate limit. If a key was rotated, update the "
                   "credential VALUE in n8n - the id does not change and no rebuild is needed."},
        {"id": "bad_request",
         "match": "400|Bad request|not valid",
         "what": "an API rejected the request we built",
         "action": "Payload or parameter defect in the failing node. Open the execution, read the "
                   "node's request body, and add a static for the shape before fixing."},
    ],
}


def node(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js):
    return node(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js})


BUILD_REPORT = r"""
const CFG = $('CONFIG').first().json;
const t = $('Error Trigger').first().json || {};
const wf = t.workflow || {};
const ex = t.execution || {};
const err = ex.error || {};
const msg = String(err.message || '');
const node = String((err.node && err.node.name) || ex.lastNodeExecuted || 'unknown');

// ---- classify against the documented dictionary
let cls = null;
for (const c of (CFG.known_classes || [])) {
  let re = null;
  try { re = new RegExp(c.match, 'i'); } catch (e) { re = null; }
  if (re && (re.test(msg) || re.test(node))) { cls = c; break; }
}

// ---- the failed execution's runData tells us what actually completed. The Error Trigger payload
// does NOT carry it, which is why v1 could never answer "was anything written?".
const fetched = (() => { try { return $json || {}; } catch (e) { return {}; } })();
const rd = (fetched && fetched.data && fetched.data.resultData
            && fetched.data.resultData.runData) || null;
const wrote = [];
let event = null, campaign = null, lead = null;
if (rd) {
  for (const w of (CFG.write_nodes || [])) if (rd[w]) wrote.push(w);
  const nz = (() => {
    try { return rd['Normalize'][0].data.main[0][0].json; } catch (e) { return null; }
  })();
  if (nz) {
    event = nz.event || null;
    campaign = nz.campaign_name || null;
    lead = (nz.lead && nz.lead.email) || null;
  }
}

const src = (CFG.sources || {})[wf.id] || null;
const label = src ? src.label : (wf.name || 'unknown workflow');

// ---- WHAT
let what = label + ' failed at "' + node + '"';
if (event) what += ' while handling a ' + event + ' event';
if (campaign) what += ' on ' + campaign;
if (lead) what += ' for ' + lead;
if (cls) what += ' - ' + cls.what;

// ---- IMPACT
let impact;
if (!rd) {
  // honest about the gap rather than guessing
  impact = 'could not read the failed execution, so writes are UNKNOWN';
} else if (wrote.length) {
  impact = 'these writes COMPLETED before the failure: ' + wrote.join(', ');
} else {
  impact = 'no write completed - it died before touching Pipedrive or Smartlead';
}
if (src) impact += '. ' + src.retry + ' -> ' + src.verdict;
else impact += '. Retry behaviour for this workflow is not documented in CONFIG';

return [{ json: {
  __what: what,
  __impact: impact,
  __action: cls ? cls.action : null,
  __class: cls ? cls.id : 'unknown',
  __unknown: !cls,
  __node: node,
  __msg: msg,
  __event: event,
  __campaign: campaign,
  __wf_id: wf.id || null,
  __wf_name: wf.name || null,
  __exec_id: ex.id || null,
  __exec_url: ex.url || null,
  __burst_key: String(wf.id || '?') + '|' + node,
} }];
"""

BURST_GATE = r"""
const CFG = $('CONFIG').first().json;
const j = $json;
const sd = $getWorkflowStaticData('global');
const store = sd.__burst = sd.__burst || {};
const windowMs = Math.max(1, Number(CFG.burst_window_minutes) || 15) * 60000;
const now = Date.now();
const st = store[j.__burst_key];
let suppress = false, carried = 0;
if (!st || (now - st.first) > windowMs) {
  // new window: report, and carry forward whatever the previous window swallowed
  carried = st ? (st.suppressed || 0) : 0;
  store[j.__burst_key] = { first: now, count: 1, suppressed: 0 };
} else {
  st.count += 1;
  st.suppressed = (st.suppressed || 0) + 1;
  suppress = true;
}
// prune keys older than 24h so this cannot grow without bound
for (const k of Object.keys(store)) {
  if ((now - (store[k].first || 0)) > 86400000) delete store[k];
}
return [{ json: { ...j, __suppress: suppress, __carried: carried,
                  __window_min: CFG.burst_window_minutes } }];
"""

LLM_BODY = r"""
const CFG = $('CONFIG').first().json;
const j = $json;
// NO secrets and NO full payloads leave here: node name, error text, event type, campaign name.
const ctx = [
  'n8n workflow: ' + (j.__wf_name || '?'),
  'failed node: ' + (j.__node || '?'),
  'error: ' + String(j.__msg || '').slice(0, 500),
  'event type: ' + (j.__event || 'n/a'),
  'campaign: ' + (j.__campaign || 'n/a'),
].join('\n');
const body = {
  model: CFG.llm.model,
  max_completion_tokens: CFG.llm.max_completion_tokens,
  response_format: { type: 'json_object' },
  messages: [
    { role: 'system', content: 'You triage n8n workflow failures for a GTM automation stack '
      + '(Smartlead email, HeyReach LinkedIn, Pipedrive CRM). Reply as JSON '
      + '{"hypothesis":"one short paragraph, most likely cause","next_check":"one concrete '
      + 'thing to look at first"}. Be specific and do not invent facts you were not given.' },
    { role: 'user', content: ctx },
  ],
};
return [{ json: { ...j, __body: body } }];
"""

COMPOSE = r"""
const j = $('Burst Gate').first().json;
// The LLM branch may not have run at all, and if it ran it may have failed - error reporting must
// never depend on it. Anything other than a clean parse degrades to the plain report.
let hypo = null, next = null;
try {
  const r = $('LLM Assist').first().json;
  const content = r && r.choices && r.choices[0] && r.choices[0].message
    ? r.choices[0].message.content : null;
  if (content) {
    const p = JSON.parse(content);
    hypo = p.hypothesis || null;
    next = p.next_check || null;
  }
} catch (e) { hypo = null; next = null; }

const lines = [];
lines.push(':boom: *WHAT*  ' + j.__what);
lines.push(':chart_with_downwards_trend: *IMPACT*  ' + j.__impact);
if (j.__action) {
  lines.push(':wrench: *ACTION*  ' + j.__action);
} else if (hypo) {
  lines.push(':wrench: *ACTION*  :robot_face: _hypothesis, not fact_ - ' + hypo
             + (next ? ('  *First check:* ' + next) : ''));
} else {
  lines.push(':wrench: *ACTION*  Unrecognised failure and no hypothesis available. '
             + 'Open the execution, identify the class, then add it to CONFIG.known_classes '
             + 'so the next occurrence is actionable.');
}
if (j.__carried > 0) {
  lines.push('_+' + j.__carried + ' more suppressed in the previous '
             + j.__window_min + '-minute window_');
}
if (j.__exec_url) lines.push('<' + j.__exec_url + '|open the failed execution>');
return [{ json: { ...j, __text: lines.join('\n'), __hypothesis: hypo } }];
"""


def build():
    N, C = [], {}
    N.append(node("e-trig", "Error Trigger", "n8n-nodes-base.errorTrigger", 1, [0, 0], {}))
    N.append(node("e-cfg", "CONFIG", "n8n-nodes-base.set", 3.4, [200, 0],
                  {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2, ensure_ascii=False),
                   "options": {}}))
    # IMPACT is impossible without runData, and the trigger does not carry it
    N.append(node("e-fetch", "Fetch Execution", "n8n-nodes-base.httpRequest", 4.2, [400, 0],
                  {"method": "GET",
                   "url": "={{ $('CONFIG').first().json.n8n_api }}"
                          "{{ '/executions/' + ($('Error Trigger').first().json.execution.id"
                          " || 0) + '?includeData=true' }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Accept",
                                                        "value": "application/json"}]},
                   "options": {},
                   "authentication": "genericCredentialType",
                   "genericAuthType": "httpHeaderAuth"},
                  credentials=N8N_CRED, retryOnFail=True, maxTries=2, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("e-build", "Build Report", [600, 0], BUILD_REPORT))
    N.append(code("e-burst", "Burst Gate", [800, 0], BURST_GATE))
    N.append(node("e-ifsup", "IF Suppressed", "n8n-nodes-base.if", 2, [1000, 0],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "e-c1",
                                                  "leftValue": "={{ $json.__suppress === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(code("e-quiet", "NoOp Suppressed", [1200, -140],
                  "return [{ json: { suppressed: true } }];"))
    N.append(node("e-ifunk", "IF Unknown Class", "n8n-nodes-base.if", 2, [1200, 80],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "e-c2",
                                                  "leftValue": "={{ $json.__unknown === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(code("e-llmbody", "LLM Body", [1400, 20], LLM_BODY))
    N.append(node("e-llm", "LLM Assist", "n8n-nodes-base.httpRequest", 4.2, [1600, 20],
                  {"method": "POST", "url": "={{ $('CONFIG').first().json.llm.base }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}, "sendBody": True, "specifyBody": "json",
                   "jsonBody": "={{ JSON.stringify($json.__body) }}",
                   "authentication": "predefinedCredentialType",
                   "nodeCredentialType": "openAiApi"},
                  credentials=LLM_CRED, retryOnFail=True, maxTries=2, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("e-compose", "Compose", [1800, 80], COMPOSE))
    N.append(node("e-slack", "WF-ERR Slack", "n8n-nodes-base.slack", 2.3, [2000, 80],
                  {"select": "channel",
                   "channelId": {"__rl": True, "mode": "id",
                                 "value": "={{ $('CONFIG').first().json.ops_channel }}"},
                   "text": "={{ $json.__text }}", "otherOptions": {}},
                  credentials=SLACK_CRED, onError="continueRegularOutput"))

    C["Error Trigger"] = {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]}
    C["CONFIG"] = {"main": [[{"node": "Fetch Execution", "type": "main", "index": 0}]]}
    C["Fetch Execution"] = {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]}
    C["Build Report"] = {"main": [[{"node": "Burst Gate", "type": "main", "index": 0}]]}
    C["Burst Gate"] = {"main": [[{"node": "IF Suppressed", "type": "main", "index": 0}]]}
    C["IF Suppressed"] = {"main": [[{"node": "NoOp Suppressed", "type": "main", "index": 0}],
                                   [{"node": "IF Unknown Class", "type": "main", "index": 0}]]}
    C["IF Unknown Class"] = {"main": [[{"node": "LLM Body", "type": "main", "index": 0}],
                                      [{"node": "Compose", "type": "main", "index": 0}]]}
    C["LLM Body"] = {"main": [[{"node": "LLM Assist", "type": "main", "index": 0}]]}
    C["LLM Assist"] = {"main": [[{"node": "Compose", "type": "main", "index": 0}]]}
    C["Compose"] = {"main": [[{"node": "WF-ERR Slack", "type": "main", "index": 0}]]}

    return {"name": "WF-ERR Error Handler", "nodes": N, "connections": C, "active": False,
            "settings": {"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner",
                         "availableInMCP": False,
                         "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all"}}


def validate(wf):
    e = []
    e.extend(item_violations(wf))
    names = [n["name"] for n in wf["nodes"]]
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    if wf.get("active") is not False:
        e.append("must ship inactive")
    # WF-ERR must NEVER chain to itself - a failing error handler that triggers itself is a loop
    if wf["settings"].get("errorWorkflow"):
        e.append("WF-ERR must not bind an errorWorkflow (self-trigger loop)")
    cfg = json.loads(next(n for n in wf["nodes"]
                          if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    if not cfg.get("known_classes"):
        e.append("known_classes empty - every failure would fall to the LLM")
    if not cfg.get("sources"):
        e.append("sources empty - IMPACT could not state retry behaviour")
    llm = next(n for n in wf["nodes"] if n["name"] == "LLM Assist")
    if llm.get("onError") != "continueRegularOutput":
        e.append("LLM Assist must not be able to break error reporting")
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.httpRequest" and "}}={{" in str(n["parameters"].get("url")):
            e.append(f"{n['name']}: welded URL (B9 class)")
    targets = {t["node"] for c in wf["connections"].values() for o in c["main"] for t in o}
    for t in targets:
        if t not in names:
            e.append(f"dangling connection target {t}")
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
    a.output.write_bytes((json.dumps(wf, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"WF-ERR v2 built -> {a.output} ({len(wf['nodes'])} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
