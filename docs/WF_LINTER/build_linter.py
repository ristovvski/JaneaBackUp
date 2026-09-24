# -*- coding: utf-8 -*-
"""Builds `dnc_wf_linter`: daily estate lint, posting ONLY new findings, to one channel only.

The rule engine is not retyped here - lint_rules.js is read verbatim and embedded, so the
scheduled workflow and the statics can never drift apart.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
LINT_CHANNEL = "C0BQM1X9ZUY"

rules_js = open(os.path.join(HERE, "lint_rules.js"), encoding="utf-8").read()
# drop the CommonJS tail; n8n has no module system
rules_js = rules_js.split("if (typeof module !==")[0].rstrip()

CONFIG = {
    # Every line of linter output goes here and nowhere else. Standing rule, 2026-08-31.
    "linter_channel": LINT_CHANNEL,
    "allowed_channels": [LINT_CHANNEL],
    "module": "dnc_wf_linter",
    "n8n_api": "https://janea-systems-2025.app.n8n.cloud/api/v1",
    "n8n_base": "https://janea-systems-2025.app.n8n.cloud",
    "max_findings_in_post": 25,
    "active_only": False,
}

N8N_CRED = {"httpHeaderAuth": {"id": "3dbKbrfihcGrOJck", "name": "n8n API (WF-2S watchdog)"}}
SLACK_CRED = {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}}

LINT_NODE_JS = rules_js + r"""

// ----------------------------------------------------------------- n8n glue
const cfg = $('CONFIG').first().json;
const resp = $input.first().json || {};
const wfs = Array.isArray(resp.data) ? resp.data : null;
const sd = $getWorkflowStaticData('global');
const now = new Date().toISOString();

// Positive shape check. An unreadable /workflows read is NOT "a clean estate" - reporting it as
// zero findings is the exact failure this linter exists to catch, so it must not commit it.
if (!wfs) {
  return [{ json: { __unreadable: true, __post: true,
    text: ':warning: *estate linter could not read the workflow list* — '
        + String((resp.error && (resp.error.message || resp.error)) || 'no data array')
        + '. No findings are being reported because none could be computed; this is not a clean run.' } }];
}

const all = lintAll(wfs);
const findings = cfg.active_only ? all.filter(f => f.active) : all;
const fp = (f) => f.workflow_id + '|' + f.node + '|' + f.rule;

const seen = sd.lint_seen = sd.lint_seen || {};
const firstEver = Object.keys(seen).length === 0;
const current = {};
findings.forEach(f => { current[fp(f)] = f; });

const fresh = findings.filter(f => !seen[fp(f)]);
const resolved = Object.keys(seen).filter(k => !current[k]);

// record state BEFORE deciding what to say, so a Slack failure cannot cause a re-post storm
findings.forEach(f => { seen[fp(f)] = seen[fp(f)] || now; });
resolved.forEach(k => { delete seen[k]; });
sd.lint_last_run = now;
sd.lint_last_counts = { scanned: wfs.length, findings: findings.length,
                        high: findings.filter(f => f.severity === 'high').length };

const sev = { high: 0, medium: 1, low: 2 };
const line = (f) => '• *' + f.severity.toUpperCase() + '* `' + f.rule + '` — '
  + (f.active ? '' : '_(inactive)_ ') + f.workflow + ' / *' + f.node + '*  `' + f.evidence + '`';

// FIRST EVER RUN: the whole backlog is "new", and dumping 190 findings into a channel is how a
// backlog gets ignored. The full report is posted once, by hand, as the standing backlog; this run
// only records the baseline and says so.
if (firstEver) {
  return [{ json: { __post: true, __seeded: findings.length,
    text: ':straight_ruler: *estate linter armed* — baseline recorded: ' + findings.length
        + ' finding(s) across ' + wfs.length + ' workflows ('
        + sd.lint_last_counts.high + ' high). These are the standing backlog and are NOT re-posted '
        + 'here; from tomorrow this channel gets only what is NEW or NEWLY RESOLVED.' } }];
}

if (!fresh.length && !resolved.length) {
  // The state-change rule applied to the linter itself: nothing changed, so nothing is said.
  return [{ json: { __post: false, __quiet: true, checked: findings.length } }];
}

const cap = Number(cfg.max_findings_in_post) || 25;
const shown = fresh.slice().sort((a, b) => sev[a.severity] - sev[b.severity]).slice(0, cap);
const parts = [];
if (fresh.length) {
  parts.push(':straight_ruler: *estate linter — ' + fresh.length + ' NEW finding(s)* ('
    + fresh.filter(f => f.severity === 'high').length + ' high) across ' + wfs.length + ' workflows');
  parts.push(shown.map(line).join('\n'));
  if (fresh.length > shown.length) {
    parts.push('_… +' + (fresh.length - shown.length) + ' more new findings not shown_');
  }
  const detail = {};
  shown.forEach(f => { detail[f.rule] = f.detail; });
  parts.push(Object.keys(detail).map(k => '`' + k + '` — ' + detail[k]).join('\n'));
}
if (resolved.length) {
  parts.push(':white_check_mark: *' + resolved.length + ' finding(s) no longer present*: '
    + resolved.slice(0, 10).map(k => '`' + k.split('|').slice(1).join('/') + '`').join(', ')
    + (resolved.length > 10 ? ' …' : ''));
}
return [{ json: { __post: true, __new: fresh.length, __resolved: resolved.length,
                  text: parts.join('\n\n').slice(0, 3800) } }];
"""

nodes = [
    {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "40 6 * * *"}]}},
     "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0],
     "id": "lint-trigger", "name": "Daily Lint Trigger"},

    {"parameters": {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2), "options": {}},
     "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [200, 0],
     "id": "lint-config", "name": "CONFIG"},

    {"parameters": {"method": "GET",
                    "url": "={{ $('CONFIG').first().json.n8n_api }}/workflows",
                    "sendQuery": True,
                    "queryParameters": {"parameters": [{"name": "limit", "value": "250"}]},
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth", "options": {}},
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [400, 0],
     "id": "lint-wflist", "name": "WF List", "onError": "continueRegularOutput",
     "credentials": N8N_CRED},

    {"parameters": {"jsCode": LINT_NODE_JS, "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 0],
     "id": "lint-engine", "name": "Lint"},

    {"parameters": {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "strict", "leftValue": "", "version": 1},
        "combinator": "and",
        "conditions": [{"id": "lint-post", "leftValue": "={{ $json.__post === true }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]},
        "options": {}},
     "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [800, 0],
     "id": "lint-if", "name": "Anything To Say"},

    {"parameters": {"jsCode":
        "// ALL linter output goes to one channel and nowhere else (standing rule, 2026-08-31).\n"
        "// Enforced here rather than trusted: a linter that leaks into #alerts or the digest is\n"
        "// exactly the noise this protocol exists to end.\n"
        "const cfg = $('CONFIG').first().json;\n"
        "const ch = cfg.linter_channel;\n"
        "if (!cfg.allowed_channels.includes(ch)) {\n"
        "  throw new Error('LINT-SEND-GUARD: linter output may only go to '\n"
        "    + cfg.allowed_channels.join(',') + ' - refused ' + ch);\n"
        "}\n"
        "return $input.all();\n", "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1000, 0],
     "id": "lint-guard", "name": "Lint Send Guard"},

    {"parameters": {"resource": "message", "operation": "post", "select": "channel",
                    "channelId": {"__rl": True, "mode": "id",
                                  "value": "={{ $('CONFIG').first().json.linter_channel }}"},
                    "text": "={{ $json.text }}",
                    "otherOptions": {"unfurl_links": False, "unfurl_media": False}},
     "type": "n8n-nodes-base.slack", "typeVersion": 2.3, "position": [1200, 0],
     "id": "lint-post", "name": "Post Lint", "credentials": SLACK_CRED},

    {"parameters": {"jsCode":
        "// Nothing new and nothing resolved. The state-change rule applies to the linter itself,\n"
        "// so it says nothing at all rather than repeating a standing backlog every morning.\n"
        "return $input.all();\n", "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1000, 200],
     "id": "lint-quiet", "name": "NoOp Nothing Changed"},
]

conns = {
    "Daily Lint Trigger": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
    "CONFIG": {"main": [[{"node": "WF List", "type": "main", "index": 0}]]},
    "WF List": {"main": [[{"node": "Lint", "type": "main", "index": 0}]]},
    "Lint": {"main": [[{"node": "Anything To Say", "type": "main", "index": 0}]]},
    "Anything To Say": {"main": [[{"node": "Lint Send Guard", "type": "main", "index": 0}],
                                 [{"node": "NoOp Nothing Changed", "type": "main", "index": 0}]]},
    "Lint Send Guard": {"main": [[{"node": "Post Lint", "type": "main", "index": 0}]]},
}

wf = {"name": "dnc_wf_linter", "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                   "callerPolicy": "workflowsFromSameOwner", "timezone": "Asia/Jerusalem"}}
json.dump(wf, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

prod = {}
for s, v in conns.items():
    for branch in v["main"]:
        for t in branch:
            prod.setdefault(t["node"], []).append(s)
print("built %d nodes; embedded rule engine %d chars" % (len(nodes), len(rules_js)))
print("fan-in:", {k: v for k, v in prod.items() if len(v) > 1} or "none")
lits = [n["name"] for n in nodes if n["name"] != "CONFIG"
        and LINT_CHANNEL in json.dumps(n["parameters"])]
print("nodes hardcoding the channel id:", lits or "none")
