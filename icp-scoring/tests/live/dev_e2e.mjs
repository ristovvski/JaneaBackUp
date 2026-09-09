#!/usr/bin/env node
// tests/live/dev_e2e.mjs — the §9.7 live suite against DEV.
//
// Asserts on EXECUTION TRUTH (which nodes ran, and what they output) rather
// than on final CRM state. Final state is polluted by co-existing automations
// seconds to hours later; what this workflow's own execution did is the only
// thing this suite can honestly claim.
//
// Prerequisites (all read from the environment; nothing is written to a file):
//   N8N_API_URL            e.g. https://n8n.internal/api/v1
//   N8N_API_KEY
//   ICP_WF_ID              the imported WF-ICP-Score workflow id in DEV
//   ICP_PATH_A_URL         the Pipedrive webhook URL (the node's production URL)
//   ICP_PATH_B_URL         the Clay callback URL
//   ICP_WEBHOOK_BASIC_USER / ICP_WEBHOOK_BASIC_PASSWORD   for Path A
//   ICP_CLAY_SECRET        the X-Clay-Secret value for Path B
//   PIPEDRIVE_API_TOKEN    to create and delete the test organizations
//
// NEEDS_DECISION #8 default: test organizations are created in the REAL
// Pipedrive account with a DEV_ name prefix and deleted at teardown. Audit
// rows are deliberately LEFT, so the run stays auditable afterwards.
//
//   npm run live
//   npm run live -- --keep     skip teardown (for debugging a failure)

import { setTimeout as sleep } from 'node:timers/promises';
import { readFileSync } from 'node:fs';

const NEEDED = [
  'N8N_API_URL', 'N8N_API_KEY', 'ICP_WF_ID', 'ICP_PATH_A_URL', 'ICP_PATH_B_URL',
  'ICP_WEBHOOK_BASIC_USER', 'ICP_WEBHOOK_BASIC_PASSWORD', 'ICP_CLAY_SECRET',
  'PIPEDRIVE_API_TOKEN',
];
const missing = NEEDED.filter((k) => !process.env[k]);
if (missing.length > 0) {
  process.stderr.write(
    `Cannot run the live suite. Missing environment: ${missing.join(', ')}\n\n` +
    'Import n8n/workflows/WF-ICP-Score.dev.json into the DEV project, register the\n' +
    'Pipedrive webhook (npm run pipedrive:webhook), and have Nik confirm the Clay\n' +
    'ICP_Engine table exists. See RUNBOOK.md.\n'
  );
  process.exit(1);
}

const KEEP = process.argv.includes('--keep');
const PD = 'https://api.pipedrive.com';
const NAME_PREFIX = `DEV_ICP_${Date.now()}`;

const results = [];
const record = (step, expected, actual, ok, note = '') =>
  results.push({ step, expected, actual, ok, note });

// --------------------------------------------------------------------------
// Clients
// --------------------------------------------------------------------------

async function pd(method, path, body = null) {
  const response = await fetch(new URL(path, PD), {
    method,
    headers: {
      'x-api-token': process.env.PIPEDRIVE_API_TOKEN,
      accept: 'application/json',
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 429) {
    await sleep(Number(response.headers.get('retry-after') || 2) * 1000);
    return pd(method, path, body);
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Pipedrive ${method} ${path} -> ${response.status}: ${text.slice(0, 300)}`);
  }
  return text ? JSON.parse(text) : {};
}

async function n8n(path, params = {}) {
  const url = new URL(`${process.env.N8N_API_URL.replace(/\/$/, '')}${path}`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const response = await fetch(url, {
    headers: { 'X-N8N-API-KEY': process.env.N8N_API_KEY, accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`n8n GET ${path} -> ${response.status}: ${(await response.text()).slice(0, 300)}`);
  }
  return response.json();
}

/** Fire a Pipedrive-shaped webhook at Path A, with basic auth. */
async function firePathA(body) {
  const auth = Buffer.from(
    `${process.env.ICP_WEBHOOK_BASIC_USER}:${process.env.ICP_WEBHOOK_BASIC_PASSWORD}`
  ).toString('base64');
  const response = await fetch(process.env.ICP_PATH_A_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Basic ${auth}` },
    body: JSON.stringify(body),
  });
  return { status: response.status, text: await response.text() };
}

/** Fire a Clay-shaped callback at Path B, with the shared-secret header. */
async function firePathB(body) {
  const response = await fetch(process.env.ICP_PATH_B_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'X-Clay-Secret': process.env.ICP_CLAY_SECRET },
    body: JSON.stringify(body),
  });
  return { status: response.status, text: await response.text() };
}

// --------------------------------------------------------------------------
// Execution truth
// --------------------------------------------------------------------------

async function executionsSince(since) {
  const payload = await n8n('/executions', {
    workflowId: process.env.ICP_WF_ID, limit: 100, includeData: true,
  });
  return (payload.data || []).filter((e) => new Date(e.startedAt).getTime() >= since);
}

/** Which nodes actually ran, and what each emitted on its first output. */
function nodeRuns(execution) {
  const runData = (execution.data && execution.data.resultData && execution.data.resultData.runData) || {};
  const out = {};
  for (const [name, runs] of Object.entries(runData)) {
    out[name] = (runs || []).map((run) => {
      const items = (run.data && run.data.main && run.data.main[0]) || [];
      return items.map((item) => item && item.json).filter(Boolean);
    });
  }
  return out;
}

const ran = (runs, node) => Object.prototype.hasOwnProperty.call(runs, node);
const firstOutput = (runs, node) => (runs[node] && runs[node][0] && runs[node][0][0]) || null;

async function waitForExecution(since, dedupeKey, { timeoutMs = 30000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const execution of await executionsSince(since)) {
      const runs = nodeRuns(execution);
      for (const node of ['Dedupe', 'Dedupe B']) {
        const output = firstOutput(runs, node);
        if (output && output._dedupe_key === dedupeKey) return { execution, runs };
      }
    }
    await sleep(1500);
  }
  return null;
}

// --------------------------------------------------------------------------
// Fixtures, retargeted at the live test organizations
// --------------------------------------------------------------------------

const dealEvent = (dealId, orgId, eventId) => ({
  meta: {
    action: 'create', entity: 'deal', entity_id: String(dealId), id: eventId,
    company_id: '0', user_id: '0', webhook_id: '0', webhook_owner_id: '0',
    correlation_id: `live-${eventId}`, attempt: 1, host: 'live.test',
    timestamp: new Date().toISOString(), type: 'general', version: '2.0',
    change_source: 'api', is_bulk_edit: false, permitted_user_ids: [],
  },
  data: { id: Number(dealId), title: `${NAME_PREFIX} deal`, org_id: Number(orgId) },
  previous: null,
});

function loadClayFixture(name, orgId, requestId, eventId) {
  const event = JSON.parse(
    readFileSync(new URL(`../fixtures/clay/${name}`, import.meta.url), 'utf8')
  );
  event.org_id = String(orgId);
  event.deal_id = null;
  event.request_id = requestId;
  event.event_id = eventId;
  event.emitted_at = new Date().toISOString();
  return event;
}

// --------------------------------------------------------------------------
// The suite
// --------------------------------------------------------------------------

const created = { orgs: [], deals: [] };

async function createOrg(name, extra = {}) {
  const org = (await pd('POST', '/api/v2/organizations', { name, ...extra })).data;
  created.orgs.push(org.id);
  return org;
}

async function createDeal(orgId, title) {
  const deal = (await pd('POST', '/api/v2/deals', { title, org_id: orgId })).data;
  created.deals.push(deal.id);
  return deal;
}

async function main() {
  process.stdout.write(`Live DEV e2e — organization prefix ${NAME_PREFIX}\n\n`);
  const t0 = Date.now() - 1000;

  // --- 1. Test organizations ---------------------------------------------
  process.stdout.write('1. creating test organizations\n');
  const orgFull = await createOrg(`${NAME_PREFIX} Full`, {
    website: 'https://akuvo.com',
    linkedin: 'https://www.linkedin.com/company/akuvo',
  });
  const orgNoWebsite = await createOrg(`${NAME_PREFIX} NoWebsite`, {
    linkedin: 'https://www.linkedin.com/company/qcash-financial',
  });
  const orgFresh = await createOrg(`${NAME_PREFIX} AlreadyScoredFresh`, {
    website: 'https://invoicecloud.com',
  });

  // Pre-score the third org so the gate has something to skip on. The field
  // keys come from the registry, so this cannot drift from what the workflow
  // reads.
  const registry = JSON.parse(
    readFileSync(new URL('../../config/pipedrive_fields.json', import.meta.url), 'utf8')
  );
  if (registry.status !== 'live') {
    throw new Error(
      'config/pipedrive_fields.json is still a placeholder. Run ' +
      'scripts/pipedrive_create_fields.mjs against the account first — the live ' +
      'suite cannot pre-score an organization with placeholder field keys.'
    );
  }
  const f = registry.fields;
  await pd('PATCH', `/api/v2/organizations/${orgFresh.id}`, {
    custom_fields: {
      [f.icp_calculated.key]: f.icp_calculated.options['ICP A'].id,
      [f.icp_score.key]: 93,
      [f.icp_scored_at.key]: new Date(Date.now() - 10 * 86400000).toISOString().slice(0, 10),
      [f.icp_model_version.key]: 'v5',
    },
  });
  record('1 create orgs', '3 orgs', `${created.orgs.length} orgs`, created.orgs.length === 3);

  // --- 2. A deal on each -------------------------------------------------
  process.stdout.write('2. creating a deal on each organization\n');
  const cases = [
    { org: orgFull, label: 'full identifiers', expectClay: true, kind: 'domain' },
    { org: orgNoWebsite, label: 'no website', expectClay: true, kind: 'linkedin' },
    { org: orgFresh, label: 'already scored, fresh', expectClay: false, kind: null },
  ];

  for (const testCase of cases) {
    const deal = await createDeal(testCase.org.id, `${NAME_PREFIX} ${testCase.label}`);
    testCase.dealId = deal.id;
    testCase.eventId = `live-a-${deal.id}`;
    const response = await firePathA(dealEvent(deal.id, testCase.org.id, testCase.eventId));
    record(`2 fire Path A (${testCase.label})`, 'HTTP 200', `HTTP ${response.status}`, response.status === 200);
  }

  await sleep(4000);

  for (const testCase of cases) {
    const key = `pipedrive:deal:${testCase.dealId}:${testCase.eventId}`;
    const found = await waitForExecution(t0, key);
    if (!found) {
      record(`2 execution (${testCase.label})`, 'an execution', 'none found', false);
      continue;
    }
    const { runs } = found;

    const deduped = firstOutput(runs, 'Dedupe');
    record(`2 Dedupe passed (${testCase.label})`, 'not a duplicate',
      String(deduped && deduped._duplicate), deduped && deduped._duplicate === false);

    const normalized = firstOutput(runs, 'Normalize');
    record(`2 Normalize (${testCase.label})`, 'create/deal, scoreable',
      normalized ? `${normalized.action}/${normalized.entity}, scoreable=${normalized.scoreable}` : 'no output',
      Boolean(normalized) && normalized.action === 'create' &&
      normalized.entity === 'deal' && normalized.scoreable === true);

    const gate = firstOutput(runs, 'IdempotencyGate');
    const expectedSkip = !testCase.expectClay;
    record(`2 gate decision (${testCase.label})`, `skip=${expectedSkip}`,
      gate ? `skip=${gate.skip} (${gate.reason})` : 'no output',
      Boolean(gate) && gate.skip === expectedSkip);

    const clayRan = ran(runs, 'POST Clay');
    record(`2 Clay POST (${testCase.label})`, testCase.expectClay ? 'exactly 1' : '0',
      clayRan ? String(runs['POST Clay'].length) : '0',
      clayRan === testCase.expectClay && (!clayRan || runs['POST Clay'].length === 1));

    if (testCase.expectClay) {
      const request = firstOutput(runs, 'BuildClayRequest');
      record(`2 identifier kind (${testCase.label})`, testCase.kind,
        request ? String(request.identifier_kind) : 'no output',
        Boolean(request) && request.identifier_kind === testCase.kind);
    }
  }

  // --- 3. Replay ---------------------------------------------------------
  process.stdout.write('3. replaying the first deal webhook\n');
  const replayCase = cases[0];
  const beforeReplay = (await executionsSince(t0)).length;
  const replayBody = dealEvent(replayCase.dealId, replayCase.org.id, replayCase.eventId);
  replayBody.meta.attempt = 2; // the only difference, exactly as Pipedrive retries
  await firePathA(replayBody);
  await sleep(4000);

  const afterReplay = await executionsSince(t0);
  const key = `pipedrive:deal:${replayCase.dealId}:${replayCase.eventId}`;
  const pastDedupe = afterReplay.filter((execution) => {
    const runs = nodeRuns(execution);
    const deduped = firstOutput(runs, 'Dedupe');
    return deduped && deduped._dedupe_key === key && ran(runs, 'Normalize');
  });
  record('3 replay dropped at Dedupe', '1 execution past Dedupe (the original)',
    String(pastDedupe.length), pastDedupe.length === 1,
    `${afterReplay.length - beforeReplay} new execution(s) started, none reached Normalize`);

  // --- 4. Path B, then the same payloads again ---------------------------
  process.stdout.write('4. posting scored events, then re-posting them\n');
  const pathBCases = [
    { fixture: 'icp_scored_A.json', org: orgFull, expectLabel: 'ICP A' },
    { fixture: 'icp_scored_insufficient.json', org: orgNoWebsite, expectLabel: 'Insufficient data' },
  ];

  for (const testCase of pathBCases) {
    const requestId = `live-b-${testCase.org.id}`;
    const eventId = `live-evt-${testCase.org.id}-0001`;
    const response = await firePathB(loadClayFixture(testCase.fixture, testCase.org.id, requestId, eventId));
    record(`4 fire Path B (${testCase.fixture})`, 'HTTP 200', `HTTP ${response.status}`, response.status === 200);
    await sleep(3000);

    const found = await waitForExecution(t0, `clay:scored:${requestId}:${eventId}`);
    if (!found) {
      record(`4 execution (${testCase.fixture})`, 'an execution', 'none found', false);
      continue;
    }
    const { runs } = found;

    const patch = firstOutput(runs, 'BuildOrgPatch');
    record(`4 patch non-empty (${testCase.fixture})`, 'a non-empty patch',
      patch ? `changed=${(patch.changed_fields || []).length}` : 'no output',
      Boolean(patch) && patch.patch_is_empty === false);
    record(`4 label (${testCase.fixture})`, testCase.expectLabel,
      patch ? String(patch.target_label) : 'no output',
      Boolean(patch) && patch.target_label === testCase.expectLabel);
    record(`4 PATCH ran (${testCase.fixture})`, 'yes',
      String(ran(runs, 'PATCH organization')), ran(runs, 'PATCH organization'));
    record(`4 note posted (${testCase.fixture})`, 'yes',
      String(ran(runs, 'POST note')), ran(runs, 'POST note'));
    record(`4 audit row (${testCase.fixture})`, 'yes',
      String(ran(runs, 'Append audit row')), ran(runs, 'Append audit row'));

    if (testCase.expectLabel === 'Insufficient data') {
      const note = firstOutput(runs, 'BuildNote');
      const missingLine = ((note && note.note) || '').split('\n')
        .find((line) => line.startsWith('Missing / low confidence:'));
      const payload = (missingLine || '').replace('Missing / low confidence:', '').trim();
      record('4 Missing line non-empty', 'non-empty',
        payload.slice(0, 40) || '(empty)', payload.length > 0);
    }

    // Same payload again: no PATCH, no second note, one extra audit row
    // flagged duplicate.
    const replay = await firePathB(loadClayFixture(testCase.fixture, testCase.org.id, requestId, eventId));
    record(`4 re-fire accepted (${testCase.fixture})`, 'HTTP 200',
      `HTTP ${replay.status}`, replay.status === 200);
    await sleep(3000);

    const duplicateRuns = (await executionsSince(t0))
      .map(nodeRuns)
      .filter((runs2) => {
        const deduped = firstOutput(runs2, 'Dedupe B');
        return deduped && deduped._dedupe_key === `clay:scored:${requestId}:${eventId}` &&
               deduped._duplicate === true;
      });

    record(`4 duplicate seen (${testCase.fixture})`, '>= 1 flagged execution',
      String(duplicateRuns.length), duplicateRuns.length >= 1);
    record(`4 duplicate: no PATCH (${testCase.fixture})`, 'PATCH did not run',
      duplicateRuns.some((r) => ran(r, 'PATCH organization')) ? 'it ran' : 'it did not',
      duplicateRuns.length > 0 && !duplicateRuns.some((r) => ran(r, 'PATCH organization')));
    record(`4 duplicate: no second note (${testCase.fixture})`, 'POST note did not run',
      duplicateRuns.some((r) => ran(r, 'POST note')) ? 'it ran' : 'it did not',
      duplicateRuns.length > 0 && !duplicateRuns.some((r) => ran(r, 'POST note')));
    const auditedDuplicate = duplicateRuns.some((r) => {
      const row = firstOutput(r, 'BuildAuditRow');
      return row && String(row.error).includes('duplicate');
    });
    record(`4 duplicate: audit row flagged (${testCase.fixture})`, 'one row flagged duplicate',
      auditedDuplicate ? 'flagged' : 'not flagged', auditedDuplicate);
  }

  // --- 5. Malformed ------------------------------------------------------
  process.stdout.write('5. posting a malformed event\n');
  const malformedRequestId = `live-b-malformed-${orgFull.id}`;
  const malformedEventId = `live-evt-malformed-${orgFull.id}`;
  const malformedResponse = await firePathB(
    loadClayFixture('icp_scored_malformed.json', orgFull.id, malformedRequestId, malformedEventId)
  );
  record('5 malformed accepted at the webhook', 'HTTP 200',
    `HTTP ${malformedResponse.status}`, malformedResponse.status === 200,
    'the webhook responds before validation, so a 200 here is correct');
  await sleep(4000);

  const malformedFound = await waitForExecution(t0, `clay:scored:${malformedRequestId}:${malformedEventId}`);
  if (malformedFound) {
    const { runs, execution } = malformedFound;
    const errorPatch = firstOutput(runs, 'BuildErrorPatch');
    record('5 BuildErrorPatch ran', 'yes', String(ran(runs, 'BuildErrorPatch')), ran(runs, 'BuildErrorPatch'));
    record('5 label Error', 'Error',
      errorPatch ? String(errorPatch.target_label) : 'no output',
      Boolean(errorPatch) && errorPatch.target_label === 'Error');
    record('5 error is the typed one', 'IcpMalformedEvent',
      errorPatch ? String(errorPatch.error_name) : 'no output',
      Boolean(errorPatch) && errorPatch.error_name === 'IcpMalformedEvent');
    record('5 Slack alert ran', 'yes',
      String(ran(runs, 'Slack alert error')), ran(runs, 'Slack alert error'));
    const slackText = JSON.stringify(runs['Slack alert error'] || []);
    record('5 alert carries execution_id', 'present',
      slackText.includes(String(execution.id)) ? 'present' : 'absent',
      slackText.includes(String(execution.id)),
      'also eyeball the message in #gtm-ops-dev');
  } else {
    record('5 malformed execution', 'an execution', 'none found', false);
  }

  // --- 6. Teardown -------------------------------------------------------
  if (KEEP) {
    process.stdout.write('\n6. --keep: leaving test organizations and deals in place\n');
    process.stdout.write(`   orgs:  ${created.orgs.join(', ')}\n   deals: ${created.deals.join(', ')}\n`);
    record('6 teardown', 'skipped (--keep)', 'skipped', true);
  } else {
    process.stdout.write('\n6. teardown (audit rows are deliberately left)\n');
    let failures = 0;
    for (const id of created.deals) {
      try { await pd('DELETE', `/api/v2/deals/${id}`); } catch (error) {
        failures += 1;
        record('6 delete deal', `deal ${id} deleted`, error.message.slice(0, 60), false);
      }
    }
    for (const id of created.orgs) {
      try { await pd('DELETE', `/api/v2/organizations/${id}`); } catch (error) {
        failures += 1;
        record('6 delete org', `org ${id} deleted`, error.message.slice(0, 60), false);
      }
    }
    record('6 teardown', 'all test deals and orgs deleted',
      `${created.deals.length} deals, ${created.orgs.length} orgs, ${failures} failure(s)`,
      failures === 0);
  }
}

// --------------------------------------------------------------------------
// Report
// --------------------------------------------------------------------------

function printTable() {
  const head = ['', 'step', 'expected', 'actual'];
  const rows = results.map((r) => [r.ok ? 'PASS' : 'FAIL', r.step, r.expected, r.actual]);
  const widths = head.map((h, i) => Math.max(h.length, ...rows.map((r) => String(r[i]).length)));
  const line = (cells) => cells.map((c, i) => String(c).padEnd(widths[i])).join('  ');

  process.stdout.write(`\n${line(head)}\n${widths.map((w) => '-'.repeat(w)).join('  ')}\n`);
  for (const row of rows) process.stdout.write(`${line(row)}\n`);

  const notes = results.filter((r) => r.note);
  if (notes.length > 0) {
    process.stdout.write('\nnotes:\n');
    for (const n of notes) process.stdout.write(`  ${n.step}: ${n.note}\n`);
  }

  const failed = results.filter((r) => !r.ok);
  process.stdout.write(`\n${results.length - failed.length}/${results.length} assertions passed.\n`);
  return failed.length;
}

try {
  await main();
} catch (error) {
  record('SUITE', 'to complete', error.message.slice(0, 160), false);
  process.stderr.write(`\nSuite aborted: ${error.stack}\n`);
  if (!KEEP) {
    process.stderr.write('Attempting teardown anyway...\n');
    for (const id of created.deals) {
      try { await pd('DELETE', `/api/v2/deals/${id}`); } catch { /* best effort */ }
    }
    for (const id of created.orgs) {
      try { await pd('DELETE', `/api/v2/organizations/${id}`); } catch { /* best effort */ }
    }
  }
}

process.exit(printTable() === 0 ? 0 : 1);
