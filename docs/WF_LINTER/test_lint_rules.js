// Statics for the estate linter. Every rule gets BOTH a fixture that must trip it and a clean
// counterpart that must not - a rule that only ever fires is as useless as one that never does.
// Fixtures are cut down from the real nodes that caused each incident.
const { lintAll } = require('./lint_rules.js');

let P = 0, F = 0;
const t = (n, c, e) => { c ? (P++, console.log('  PASS  ' + n))
                           : (F++, console.log('  FAIL  ' + n + (e !== undefined ? '  ' + JSON.stringify(e) : ''))); };
const wf = (name, nodes, connections, active) =>
  ({ id: 'w_' + name, name, active: active !== false, nodes, connections: connections || {} });
const codeN = (name, js) => ({ name, type: 'n8n-nodes-base.code', parameters: { jsCode: js } });
const httpN = (name, params) => ({ name, type: 'n8n-nodes-base.httpRequest', parameters: params });
const dtN = (name, mode, value) => ({ name, type: 'n8n-nodes-base.dataTable',
  parameters: { dataTableId: { __rl: true, mode, value }, operation: 'get' } });
const ifN = (name, cond) => ({ name, type: 'n8n-nodes-base.if', parameters: { conditions: cond } });
const slackN = (name, ch) => ({ name, type: 'n8n-nodes-base.slack',
  parameters: { channelId: { __rl: true, mode: 'id', value: ch }, text: '=x' } });
const schedN = (name) => ({ name, type: 'n8n-nodes-base.scheduleTrigger',
  parameters: { rule: { interval: [{ field: 'minutes', minutesInterval: 15 }] } } });
const link = (a, b, oi, ii) => ({ [a]: { main: Array.from({ length: (oi || 0) + 1 },
  (_, i) => i === (oi || 0) ? [{ node: b, type: 'main', index: ii || 0 }] : []) } });
const rules = (f) => f.map(x => x.rule);
const has = (f, r) => f.some(x => x.rule === r);

// ---------------------------------------------------------------- R01
console.log('\n[R01] __field read after a replacing node');
{
  // the real Finovate shape: Body Lead Create reads $json.__person_id, fed через a lead-list HTTP
  const bad = wf('b12', [httpN('Lead List', { url: 'https://x/v1/leads?person_id=1&sort=a' }),
                         codeN('Body Lead Create', 'const p = $json.__person_id; return [];')],
                 link('Lead List', 'Body Lead Create'));
  const f = lintAll([bad]);
  t('fires on an immediate HTTP hop', has(f, 'R01_b12_field_after_replacing_node'), rules(f));
  t('rated high at one hop',
    f.filter(x => x.rule === 'R01_b12_field_after_replacing_node')[0].severity === 'high');

  // through a pass-through IF - the shape that hid it
  const thru = wf('b12b', [httpN('Deal List', { url: 'https://x/api/v2/deals' }),
                           ifN('IF No Lead', {}),
                           codeN('Reader', 'const v = $json.__lead_id; return [];')],
    Object.assign(link('Deal List', 'IF No Lead'), link('IF No Lead', 'Reader')));
  const f2 = lintAll([thru]);
  t('fires through a pass-through IF', has(f2, 'R01_b12_field_after_replacing_node'), rules(f2));
  t('rated medium when separated by pass-throughs',
    f2.filter(x => x.rule === 'R01_b12_field_after_replacing_node')[0].severity === 'medium');

  // clean: the writer is the immediate code ancestor
  const ok = wf('b12ok', [codeN('Writer', 'return [{json:{__person_id: 1}}];'),
                          codeN('Reader', 'const p = $json.__person_id; return [];')],
               link('Writer', 'Reader'));
  t('silent when a code node upstream writes the field',
    !has(lintAll([ok]), 'R01_b12_field_after_replacing_node'), rules(lintAll([ok])));
}

// ---------------------------------------------------------------- R02
console.log('\n[R02] fan-in treated as a join');
{
  const bad = wf('fanin', [codeN('A', 'return [];'), codeN('B', 'return [];'),
                           codeN('Summarize', "const w = $('A').first().json; return [];")],
    { A: { main: [[{ node: 'Summarize', type: 'main', index: 0 }]] },
      B: { main: [[{ node: 'Summarize', type: 'main', index: 0 }]] } });
  const f = lintAll([bad]);
  t('fires on two producers into one input', has(f, 'R02_fan_in_treated_as_join'), rules(f));
  t('rated high when the target reads a producer by name',
    f.filter(x => x.rule === 'R02_fan_in_treated_as_join')[0].severity === 'high');

  // the LEGITIMATE shape: one node's success AND error output into the same input
  const ok = wf('pair', [dtN('Row', 'id', 'abc'), codeN('Load', 'return [];')],
    { Row: { main: [[{ node: 'Load', type: 'main', index: 0 }],
                    [{ node: 'Load', type: 'main', index: 0 }]] } });
  t('silent on a success/error pair from ONE node',
    !has(lintAll([ok]), 'R02_fan_in_treated_as_join'), rules(lintAll([ok])));
}

// ---------------------------------------------------------------- R03
console.log('\n[R03] IF false-branch wired as if it were true');
{
  const cond = { conditions: [{ leftValue: '={{ $json.should_alert_queue }}' }] };
  const bad = wf('ifq', [ifN('Queue Stuck?', cond), slackN('Alert: Queue Stuck', 'C0AAAAAAAAA')],
    { 'Queue Stuck?': { main: [[], [{ node: 'Alert: Queue Stuck', type: 'main', index: 0 }]] } });
  const f = lintAll([bad]);
  t('fires when only output 1 is wired', has(f, 'R03_if_false_branch_used_as_true'), rules(f));
  t('rated high for a positive condition driving an action',
    f.filter(x => x.rule === 'R03_if_false_branch_used_as_true')[0].severity === 'high');

  const ok = wf('ifok', [ifN('Healthy?', cond), slackN('Alert', 'C0AAAAAAAAA')],
    { 'Healthy?': { main: [[{ node: 'Alert', type: 'main', index: 0 }], []] } });
  t('silent when output 0 is wired',
    !has(lintAll([ok]), 'R03_if_false_branch_used_as_true'));
}

// ---------------------------------------------------------------- R04 / R05
console.log('\n[R04/R05] dataTable failure read as absence; missing read as zero');
{
  const bad = wf('dt', [dtN('Check Queue', 'id', 'abc'),
                        codeN('Depth', 'const rows=$input.all(); const depth=rows.length; return [{json:{depth}}];')],
                link('Check Queue', 'Depth'));
  const f = lintAll([bad]);
  t('R04 fires with no positive shape check', has(f, 'R04_datatable_error_read_as_absence'), rules(f));
  t('R05 fires on a .length count with no null', has(f, 'R05_missing_read_as_zero'), rules(f));

  const ok = wf('dtok', [dtN('Check Queue', 'id', 'abc'),
    codeN('Depth', "const rows=$input.all().map(i=>i.json).filter(r=>r&&typeof r.row_key==='string');"
                 + ' const depth = rows.length ? rows.length : null; return [{json:{depth}}];')],
                link('Check Queue', 'Depth'));
  const f2 = lintAll([ok]);
  t('R04 silent with a typeof shape check', !has(f2, 'R04_datatable_error_read_as_absence'), rules(f2));
  t('R05 silent when null is reachable', !has(f2, 'R05_missing_read_as_zero'), rules(f2));
}

// ---------------------------------------------------------------- R06
console.log('\n[R06] hardcoded channel id');
{
  const bad = wf('ch', [slackN('Post', 'C0BTP6VHP1B')]);
  t('fires on a literal id in a Slack node', has(lintAll([bad]), 'R06_hardcoded_channel_id'));
  const ok = wf('chok', [slackN('Post', "={{ $('CONFIG').first().json.digest_channel }}")]);
  t('silent when the id comes from CONFIG', !has(lintAll([ok]), 'R06_hardcoded_channel_id'));
  const cfg = wf('chcfg', [{ name: 'CONFIG', type: 'n8n-nodes-base.set',
    parameters: { mode: 'raw', jsonOutput: '{"c":"C0BTP6VHP1B"}' } }]);
  t('CONFIG itself is exempt', !has(lintAll([cfg]), 'R06_hardcoded_channel_id'));
}

// ---------------------------------------------------------------- R08
console.log('\n[R08] Set node dropping carried fields');
{
  const bad = wf('set', [{ name: 'S', type: 'n8n-nodes-base.set',
    parameters: { assignments: { assignments: [{ name: 'a', value: '1' }] } } }]);
  t('fires without includeOtherFields', has(lintAll([bad]), 'R08_set_drops_carried_fields'));
  const ok = wf('setok', [{ name: 'S', type: 'n8n-nodes-base.set',
    parameters: { includeOtherFields: true, assignments: { assignments: [] } } }]);
  t('silent with includeOtherFields', !has(lintAll([ok]), 'R08_set_drops_carried_fields'));
  const raw = wf('setraw', [{ name: 'S', type: 'n8n-nodes-base.set',
    parameters: { mode: 'raw', jsonOutput: '{}' } }]);
  t('silent in raw mode', !has(lintAll([raw]), 'R08_set_drops_carried_fields'));
}

// ---------------------------------------------------------------- R09 / R10 / R12
console.log('\n[R09/R10/R12] provider-endpoint traps');
{
  const bad = wf('pd', [httpN('Leads', { url: 'https://api.pipedrive.com/v1/leads',
    sendQuery: true, queryParameters: { parameters: [{ name: 'limit', value: '100' }] } })]);
  t('R09 fires on /v1/leads with no sort', has(lintAll([bad]), 'R09_v1_leads_without_sort'));
  const ok = wf('pdok', [httpN('Leads', { url: 'https://api.pipedrive.com/v1/leads',
    sendQuery: true, queryParameters: { parameters: [{ name: 'sort', value: 'add_time DESC' }] } })]);
  t('R09 silent with a sort', !has(lintAll([ok]), 'R09_v1_leads_without_sort'));
  const one = wf('pdone', [httpN('Lead', { url: "=https://api.pipedrive.com/v1/leads/{{ $json.id }}" })]);
  t('R09 silent on a single-lead GET', !has(lintAll([one]), 'R09_v1_leads_without_sort'), rules(lintAll([one])));

  const big = wf('lim', [httpN('Search', { url: 'https://api.pipedrive.com/api/v2/leads/search',
    sendQuery: true, queryParameters: { parameters: [{ name: 'limit', value: '500' }] } })]);
  t('R10 fires on limit=500', has(lintAll([big]), 'R10_limit_over_cap'));
  const small = wf('limok', [httpN('Search', { url: 'https://api.pipedrive.com/api/v2/leads/search',
    sendQuery: true, queryParameters: { parameters: [{ name: 'limit', value: '100' }] } })]);
  t('R10 silent at 100', !has(lintAll([small]), 'R10_limit_over_cap'));

  const ex = wf('ex', [httpN('Execs', { url: 'https://n8n/api/v1/executions?limit=250' })]);
  t('R12 fires on an unfiltered /executions read', has(lintAll([ex]), 'R12_executions_without_status'));
  const exok = wf('exok', [httpN('Execs', { url: 'https://n8n/api/v1/executions',
    sendQuery: true, queryParameters: { parameters: [{ name: 'status', value: 'error' }] } })]);
  t('R12 silent with status=', !has(lintAll([exok]), 'R12_executions_without_status'));
}

// ---------------------------------------------------------------- R11
console.log('\n[R11] existence guard that forgets the campaign');
{
  const bad = wf('guard', [codeN('Guard',
    'const hasLead = leads.length > 0; if (hasLead) return []; return [1];')]);
  t('fires when no campaign scoping is present', has(lintAll([bad]), 'R11_existence_guard_ignores_campaign'));
  const ok = wf('guardok', [codeN('Guard',
    'const hit = mine.find(l => l.campaign_name === n.campaign_name); const hasLead = !!hit;')]);
  t('silent when the guard is campaign-scoped', !has(lintAll([ok]), 'R11_existence_guard_ignores_campaign'));
}

// ---------------------------------------------------------------- R13
console.log('\n[R13] dataTable by name');
{
  t('fires on mode:name', has(lintAll([wf('dtn', [dtN('T', 'name', 'dnc_gate_queue')])]),
    'R13_datatable_by_name'));
  t('silent on mode:id', !has(lintAll([wf('dti', [dtN('T', 'id', 'UOgKwl')])]),
    'R13_datatable_by_name'));
}

// ---------------------------------------------------------------- R07
console.log('\n[R07] scheduled alert with no state memory');
{
  // the real defect shape: a CONDITIONAL post on a poll, with nothing remembering the last verdict
  const bad = wf('poll', [schedN('T'), codeN('Eval', 'return [];'), ifN('Bad?', {}),
                          slackN('Alert', "={{ $('CONFIG').first().json.c }}")],
    Object.assign(link('T', 'Eval'), link('Eval', 'Bad?'), link('Bad?', 'Alert')));
  t('fires on a conditional poll alert with no state',
    has(lintAll([bad]), 'R07_poll_alert_without_state_change'), rules(lintAll([bad])));
  const ok = wf('pollok', [schedN('T'),
    codeN('Eval', 'const sd=$getWorkflowStaticData("global"); return [];'), ifN('Bad?', {}),
    slackN('Alert', "={{ $('CONFIG').first().json.c }}")],
    Object.assign(link('T', 'Eval'), link('Eval', 'Bad?'), link('Bad?', 'Alert')));
  t('silent when static data gates the alert', !has(lintAll([ok]), 'R07_poll_alert_without_state_change'));
  // an UNCONDITIONAL daily digest is supposed to repeat - "silence must never be ambiguous"
  const digest = wf('digest', [schedN('T'), codeN('Compose', 'return [];'),
                               slackN('Post Digest', "={{ $('CONFIG').first().json.c }}")],
    Object.assign(link('T', 'Compose'), link('Compose', 'Post Digest')));
  t('silent for an unconditional periodic digest',
    !has(lintAll([digest]), 'R07_poll_alert_without_state_change'), rules(lintAll([digest])));
  const wh = wf('webhook', [{ name: 'W', type: 'n8n-nodes-base.webhook', parameters: {} },
    slackN('Alert', "={{ $('CONFIG').first().json.c }}")], link('W', 'Alert'));
  t('silent for a webhook-triggered alert (no poll to repeat)',
    !has(lintAll([wh]), 'R07_poll_alert_without_state_change'));
}

// ---------------------------------------------------------------- R14
console.log('\n[R14] Responded written with no engagement gate');
{
  const RESP = 'c9d4b550-bcf3-11ef-a843-357f91e826ec';
  // the real node, verbatim in shape: builds a PATCH body from an ungated target set
  const bad = wf('resp', [codeN('Body U Lead DNC Label',
    "const target=[CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];\n"
    + "const union = existing.slice(); for (const id of target) union.push(id);\n"
    + "const body = { label_ids: union }; return [{json:{__body: body}}];")]);
  t('fires on an unconditional Responded write', has(lintAll([bad]), 'R14_responded_without_engagement_gate'),
    rules(lintAll([bad])));
  const ok = wf('respok', [codeN('Union',
    "const target = __isBounce ? [CFG.labels.cold] : [CFG.labels.cold, CFG.labels.responded];")]);
  t('silent when a bounce gate is present', !has(lintAll([ok]), 'R14_responded_without_engagement_gate'));
  const ok2 = wf('respok2', [codeN('M7 Labels Compute',
    "const effectiveRank = Math.max(currentRank, incomingRank); const l = CFG.labels.responded;")]);
  t('silent for the LinkedIn stage-rank path (a reply IS the signal)',
    !has(lintAll([ok2]), 'R14_responded_without_engagement_gate'));
  const reader = wf('respread', [codeN('Quality Digest',
    "const n = leads.filter(l => (l.label_ids||[]).includes('c9d4b550-bcf3-11ef-a843-357f91e826ec')).length;")]);
  t('silent for a node that only READS label_ids to count',
    !has(lintAll([reader]), 'R14_responded_without_engagement_gate'));
  const cfg = wf('respcfg', [{ name: 'CONFIG', type: 'n8n-nodes-base.set',
    parameters: { mode: 'raw', jsonOutput: JSON.stringify({ labels: { responded: RESP } }) } }]);
  t('CONFIG declaring the label map is not a write',
    !has(lintAll([cfg]), 'R14_responded_without_engagement_gate'));
}

// ---------------------------------------------------------------- R16
console.log('\n[R16] settings key rejected by the PUT API');
{
  const bad = { id: 'w_s', name: 'x', active: true, nodes: [], connections: {},
                settings: { executionOrder: 'v1', timeSavedMode: 'fixed' } };
  t('fires on timeSavedMode', has(lintAll([bad]), 'R16_settings_key_rejected_by_put_api'));
  const ok = { id: 'w_s2', name: 'y', active: true, nodes: [], connections: {},
               settings: { executionOrder: 'v1' } };
  t('silent without it', !has(lintAll([ok]), 'R16_settings_key_rejected_by_put_api'));
  const none = { id: 'w_s3', name: 'z', active: true, nodes: [], connections: {} };
  t('silent with no settings at all', !has(lintAll([none]), 'R16_settings_key_rejected_by_put_api'));
}

// ---------------------------------------------------------------- shape of the output
console.log('\n[shape] findings are addressable');
{
  const f = lintAll([wf('dtn', [dtN('T', 'name', 'q')])]);
  const x = f[0];
  t('carries workflow, id, node, severity, detail',
    x.workflow && x.workflow_id && x.node && x.severity && x.detail && 'active' in x, x);
  t('severity is one of high/medium', ['high', 'medium', 'low'].indexOf(x.severity) !== -1);
}

// ---------------------------------------------------------------- comments are not code
console.log('\n[comments] rules scan code with comments stripped');
{
  const { stripJsComments: s } = require('./lint_rules.js');
  const cases = [
    ['line comment removed', 'const a = 1; // C0B8GCVNR5W\nconst b = 2;', 'const a = 1; \nconst b = 2;'],
    ['block comment blanked, newlines kept', 'a /* x\n y */ b', 'a     \n      b'],
    ['// inside a single-quoted URL kept', "const u = 'https://api.pipedrive.com'; // t", "const u = 'https://api.pipedrive.com'; "],
    ['// inside a double-quoted string kept', 'x = "//not a comment"', 'x = "//not a comment"'],
    ['template literal kept', 'x = `a // b ${c}`', 'x = `a // b ${c}`'],
    ['regex literal with slashes kept', String.raw`const r = /\/\/+/g; // c`, String.raw`const r = /\/\/+/g; `],
    ['regex after return kept', String.raw`return /a\/\/b/.test(x) // c`, String.raw`return /a\/\/b/.test(x) `],
    ['regex class with a slash kept', 'const r = /[/]x/; // c', 'const r = /[/]x/; '],
    ['division is not a regex', 'const d = a / b / c; // x', 'const d = a / b / c; '],
    ['escaped quote does not end the string', String.raw`s = 'it\'s // fine'; // gone`, String.raw`s = 'it\'s // fine'; `],
    ['several strings in a row', "a('x'); b('y'); // $('Gone')", "a('x'); b('y'); "],
  ];
  cases.forEach(([name, inp, want]) => { const got = s(inp); t(name, got === want, got); });

  // R06: a channel id that only appears in a comment is not a hardcoded channel
  const commentOnly = wf('r06c', [codeN('Route', '// used to post to C0B8GCVNR5W\nreturn [];')]);
  t('R06 silent when the channel id is only in a comment', !has(lintAll([commentOnly]), 'R06_hardcoded_channel_id'));
  const inCode = wf('r06k', [codeN('Route', "const ch = 'C0B8GCVNR5W';\nreturn [];")]);
  t('R06 still fires on a channel id in code', has(lintAll([inCode]), 'R06_hardcoded_channel_id'));
  // R05: a `null` that only appears in a comment must not satisfy the rule
  const nullInComment = wf('r05c', [httpN('Read', { url: 'https://x/y' }),
    codeN('Count', '// returns null when unreadable\nreturn [{ json: { n: $input.all().length } }];')],
    link('Read', 'Count'));
  t('R05 fires when the only `null` is in a comment', has(lintAll([nullInComment]), 'R05_missing_read_as_zero'));
}

console.log('\n==== ' + P + ' passed, ' + F + ' failed');
process.exit(F ? 1 : 0);
