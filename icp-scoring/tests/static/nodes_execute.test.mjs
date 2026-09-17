// tests/static/nodes_execute.test.mjs — the §9.4 case table, run against the
// REAL Code-node sources with a mocked n8n scope.
//
// Every case here is a behaviour someone could remove. If a case can be
// deleted from a node without a test going red, the test is decoration.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

import {
  runCodeNode, readNode, makeConfig, orgFixture, clayFixture, pipedriveFixture, NOW_ISO,
} from './harness.mjs';
import { score } from '../../engine/scoring.mjs';
import { resolveIdentifier } from '../../engine/normalize.mjs';
import { activationStateFor } from '../../engine/activation_guard.mjs';

/** Every fixture that is supposed to validate. The malformed one is not here. */
const VALID_FIXTURES = [
  'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting_valid.json',
  'icp_scored_contracting_unbacked.json', 'icp_scored_insufficient.json',
  'icp_scored_tier2.json', 'icp_scored_unknown_vertical.json',
];

const SRC = {
  Dedupe: readNode('Dedupe'),
  Normalize: readNode('Normalize'),
  IdempotencyGate: readNode('IdempotencyGate'),
  BuildClayRequest: readNode('BuildClayRequest'),
  ParseScored: readNode('ParseScored'),
  Score: readNode('Score'),
  BuildOrgPatch: readNode('BuildOrgPatch'),
  BuildNote: readNode('BuildNote'),
  BuildAuditRow: readNode('BuildAuditRow'),
  BuildErrorPatch: readNode('BuildErrorPatch'),
};

const cfg = makeConfig();

// --------------------------------------------------------------------------
// Small drivers, so each case reads as the behaviour it asserts.
// --------------------------------------------------------------------------

const dedupeA = (body, staticData) => runCodeNode(SRC.Dedupe, {
  nodes: { CONFIG: cfg, 'Webhook Pipedrive': { body } },
  staticData,
});

const dedupeB = (body, staticData) => runCodeNode(SRC.Dedupe, {
  nodes: { CONFIG: cfg, 'Webhook Clay': { body } },
  staticData,
});

// runCodeNode wraps each input element in { json }, so hand it the raw json.
const normalize = (dedupeItem) => runCodeNode(SRC.Normalize, {
  input: [dedupeItem.json],
  nodes: { CONFIG: cfg },
});

const gate = (normalized, org) => runCodeNode(SRC.IdempotencyGate, {
  input: [org],
  nodes: { CONFIG: cfg, Normalize: normalized },
});

const clayRequest = (gateOut) => runCodeNode(SRC.BuildClayRequest, {
  nodes: { CONFIG: cfg, IdempotencyGate: gateOut },
});

const parseScored = (event, staticData) => {
  const [deduped] = dedupeB(event, staticData || {});
  return runCodeNode(SRC.ParseScored, { input: [deduped.json], nodes: { CONFIG: cfg } });
};

// Score runs on ParseScored's output and hands the same object on with a
// `score` added, so everything downstream reads one node.
const scoreNode = (parsed) => runCodeNode(SRC.Score, {
  input: [parsed],
  nodes: { CONFIG: cfg },
});

/** The whole Path B head: dedupe -> parse -> score. */
const scored = (eventName, staticData) => {
  const event = typeof eventName === 'string' ? clayFixture(eventName) : eventName;
  const [parsed] = parseScored(event, staticData);
  return scoreNode(parsed.json)[0].json;
};

const orgPatch = (out, org) => runCodeNode(SRC.BuildOrgPatch, {
  input: [org],
  nodes: { CONFIG: cfg, Score: out },
});

const buildNote = (out) => runCodeNode(SRC.BuildNote, {
  nodes: { CONFIG: cfg, Score: out },
});

const auditRow = (out, extra = {}) => runCodeNode(SRC.BuildAuditRow, {
  nodes: { CONFIG: cfg, Score: out, ...extra },
});

// ==========================================================================
describe('Dedupe', () => {
  test('deal.create passes and carries a Pipedrive-shaped key', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    const [out] = dedupeA(body, {});
    assert.equal(out.json._path, 'A');
    assert.equal(out.json._duplicate, false);
    assert.equal(out.json._dedupe_key, 'pipedrive:deal:55001:evt-2026-09-09-000111');
  });

  test('replay dropped — Dedupe returns [] on the second delivery (Path A)', () => {
    const staticData = {};
    const first = dedupeA(pipedriveFixture('deal_added.v2.json'), staticData);
    assert.equal(first.length, 1, 'the first delivery must pass');

    const replay = dedupeA(pipedriveFixture('deal_added.replay.json'), staticData);
    assert.deepEqual(replay, [], 'the replay must be dropped, with nothing downstream');
  });

  test('the key ignores meta.attempt, which is what makes the replay a replay', () => {
    const original = pipedriveFixture('deal_added.v2.json');
    const replay = pipedriveFixture('deal_added.replay.json');
    assert.notEqual(original.meta.attempt, replay.meta.attempt, 'the fixtures must differ on attempt');
    assert.equal(original.meta.id, replay.meta.id);
    const [a] = dedupeA(original, {});
    const [b] = dedupeA(replay, {});
    assert.equal(a.json._dedupe_key, b.json._dedupe_key);
  });

  test('a Clay duplicate passes through flagged, so the audit row still happens', () => {
    const staticData = {};
    const event = clayFixture('icp_scored_A.json');
    const first = dedupeB(event, staticData);
    assert.equal(first[0].json._duplicate, false);

    const second = dedupeB(event, staticData);
    assert.equal(second.length, 1, 'a Path B duplicate must NOT be dropped');
    assert.equal(second[0].json._duplicate, true);
    // v6 sends no event_id, so the key is request_id with a placeholder half.
    assert.equal(second[0].json._dedupe_key, 'clay:scored:req-icp-0001:-');
  });

  test('two different events do not collide', () => {
    const staticData = {};
    dedupeB(clayFixture('icp_scored_A.json'), staticData);
    const [other] = dedupeB(clayFixture('icp_scored_B_stable.json'), staticData);
    assert.equal(other.json._duplicate, false);
  });

  test('the ledger is pruned past its TTL', () => {
    const staticData = {};
    dedupeA(pipedriveFixture('deal_added.v2.json'), staticData);
    const key = 'pipedrive:deal:55001:evt-2026-09-09-000111';
    assert.ok(staticData.global.seen[key]);
    // Age it past the TTL and re-deliver: it must pass again, not be dropped
    // forever by a ledger that never forgets.
    staticData.global.seen[key] = Date.now() - (cfg.dedupe_ttl_hours + 1) * 3600 * 1000;
    const again = dedupeA(pipedriveFixture('deal_added.v2.json'), staticData);
    assert.equal(again.length, 1);
  });

  test('a Clay callback with no request_id throws rather than poisoning the ledger', () => {
    // v5 needed request_id AND event_id. v6 sends no event_id at all, so the
    // key is request_id plus whatever event_id happens to be there — and
    // request_id alone is now the thing that must never be missing, because
    // without it every callback shares one key and all but the first is
    // silently dropped.
    const event = clayFixture('icp_scored_A.json');
    delete event.request_id;
    assert.throws(() => dedupeB(event, {}), /ICP_MALFORMED_EVENT/);
  });

  test('an event_id, when the table sends one, separates two runs of the same request', () => {
    const staticData = {};
    const first = clayFixture('icp_scored_A.json');
    first.event_id = 'run-1';
    const second = clayFixture('icp_scored_A.json');
    second.event_id = 'run-2';
    assert.equal(dedupeB(first, staticData)[0].json._duplicate, false);
    assert.equal(dedupeB(second, staticData)[0].json._duplicate, false, 'a second run is not a duplicate');
    assert.equal(dedupeB(second, staticData)[0].json._duplicate, true, 'the same run twice is');
  });

  test('the path is read from the webhook above, not from a key in the body', () => {
    // v5 detected Path B by `event === "icp.scored"`; v6's consolidated event
    // has no such key. An empty body down the Clay webhook must still be
    // recognised as Path B — and fail for the right reason.
    assert.throws(() => dedupeB({}, {}), /ICP_MALFORMED_EVENT/);
    // And a Path B body arriving down the Pipedrive webhook is a Path A
    // delivery with no meta.id, which is the other error entirely.
    assert.throws(() => dedupeA(clayFixture('icp_scored_A.json'), {}), /ICP_UNKNOWN_PAYLOAD/);
  });

  test('an unrecognised body throws — both endpoints are authenticated, so it is real', () => {
    assert.throws(() => dedupeA({ hello: 'world' }, {}), /ICP_UNKNOWN_PAYLOAD/);
  });

  test('the anomaly gate counts events and flips past the configured rate', () => {
    const staticData = {};
    let last;
    for (let i = 0; i < cfg.max_events_per_hour + 1; i += 1) {
      const body = structuredClone(pipedriveFixture('deal_added.v2.json'));
      body.meta.id = `evt-${i}`;
      last = dedupeA(body, staticData)[0];
    }
    assert.equal(last.json._rate_exceeded, true);
    assert.equal(last.json._rate_this_hour, cfg.max_events_per_hour + 1);
  });
});

// ==========================================================================
describe('Normalize', () => {
  test('deal.create emits action, entity, deal_id and org_id', () => {
    const [deduped] = dedupeA(pipedriveFixture('deal_added.v2.json'), {});
    const [out] = normalize(deduped);
    assert.equal(out.json.action, 'create');
    assert.equal(out.json.entity, 'deal');
    assert.equal(out.json.deal_id, '55001');
    assert.equal(out.json.org_id, '10001');
    assert.equal(out.json.scoreable, true);
    assert.equal(out.json.skip_reason, null);
  });

  test('deal.update is ignored — the IF gate routes it to NoOp', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    body.meta.action = 'change';
    const [deduped] = dedupeA(body, {});
    const [out] = normalize(deduped);
    assert.equal(out.json.scoreable, false, 'the IF gate reads scoreable');
    assert.match(out.json.skip_reason, /not the trigger event/);
  });

  test('a deal.delete is ignored too', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    body.meta.action = 'delete';
    const [out] = normalize(dedupeA(body, {})[0]);
    assert.equal(out.json.scoreable, false);
  });

  test('an event on another entity is ignored', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    body.meta.entity = 'person';
    const [out] = normalize(dedupeA(body, {})[0]);
    assert.equal(out.json.scoreable, false);
  });

  test('a deal with no organization is skipped, not errored', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    body.data.org_id = null;
    const [out] = normalize(dedupeA(body, {})[0]);
    assert.equal(out.json.scoreable, false);
    assert.match(out.json.skip_reason, /no org_id/);
  });

  test('request_id prefers the Pipedrive correlation id and is stable across retries', () => {
    const [a] = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0]);
    const [b] = normalize(dedupeA(pipedriveFixture('deal_added.replay.json'), {})[0]);
    assert.equal(a.json.request_id, b.json.request_id);
    assert.match(a.json.request_id, /^req-b7f2c1a0/);
  });

  test('request_id falls back to the event id when there is no correlation id', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    delete body.meta.correlation_id;
    const [out] = normalize(dedupeA(body, {})[0]);
    assert.equal(out.json.request_id, 'req-deal-55001-evt-2026-09-09-000111');
  });

  test('it reads is_bulk_edit, the name the v2 guide actually documents', () => {
    const body = pipedriveFixture('deal_added.v2.json');
    body.meta.is_bulk_edit = true;
    const [out] = normalize(dedupeA(body, {})[0]);
    assert.equal(out.json.is_bulk_edit, true);
  });
});

// ==========================================================================
describe('IdempotencyGate', () => {
  const normalized = () => normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;

  test('fresh score -> skip true', () => {
    const { org } = orgFixture('org_already_scored_fresh.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, true);
    assert.match(out.json.reason, /fresh/);
    assert.equal(out.json.existing.age_days, 10);
  });

  test('stale score (200 days) -> skip false', () => {
    const { org } = orgFixture('org_already_scored_stale.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false);
    assert.match(out.json.reason, /stale/);
    assert.equal(out.json.existing.age_days, 200);
  });

  test('old model (v5) inside the window -> skip false', () => {
    const { org } = orgFixture('org_scored_old_model.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false, 'a date-only gate would wrongly skip this');
    assert.match(out.json.reason, /model version "v5"/);
    assert.equal(out.json.existing.age_days, 10);
  });

  test('never scored -> skip false', () => {
    const { org } = orgFixture('org_full.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false);
    assert.match(out.json.reason, /never scored/);
  });

  test('a previous Error does not freeze the org out of scoring for 180 days', () => {
    const { org } = orgFixture('org_already_scored_fresh.json', cfg);
    org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated.Error;
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false);
    assert.match(out.json.reason, /not a grade/);
  });

  test('a previous Insufficient data is retried too', () => {
    const { org } = orgFixture('org_already_scored_fresh.json', cfg);
    org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated['Insufficient data'];
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false);
  });

  test('the literal §8.1 reading is one CONFIG flag away', () => {
    const strict = makeConfig({ rescore_on_error_or_insufficient: false });
    const { org } = orgFixture('org_already_scored_fresh.json', strict);
    org.custom_fields[strict.f_icp_calculated] = strict.opt_icp_calculated.Error;
    const [out] = runCodeNode(SRC.IdempotencyGate, {
      input: [org],
      nodes: { CONFIG: strict, Normalize: normalized() },
    });
    assert.equal(out.json.skip, true, 'with the flag off, any present value counts as scored');
  });

  test('exactly at the window boundary the score is stale, not fresh', () => {
    const { org } = orgFixture('org_already_scored_fresh.json', cfg);
    const boundary = new Date(new Date(NOW_ISO).getTime() - cfg.rescore_after_days * 86400000);
    org.custom_fields[cfg.f_icp_scored_at] = boundary.toISOString().slice(0, 10);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.existing.age_days, cfg.rescore_after_days);
    assert.equal(out.json.skip, false, `${cfg.rescore_after_days} days is not < ${cfg.rescore_after_days}`);
  });

  test('a garbled scored_at re-scores rather than skipping', () => {
    const { org } = orgFixture('org_already_scored_fresh.json', cfg);
    org.custom_fields[cfg.f_icp_scored_at] = 'not a date';
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false);
    assert.match(out.json.reason, /no usable ICP Scored At/);
  });

  test('the gate carries the identifier fields BuildClayRequest needs', () => {
    const { org } = orgFixture('org_full.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.org_name, 'Akuvo, Inc.');
    assert.equal(out.json.org_website, 'https://www.akuvo.com/');
    assert.equal(out.json.org_country, 'United States');
    assert.equal(out.json.org_state, 'Colorado');
  });
});

// ==========================================================================
describe('BuildClayRequest — identifier priority', () => {
  const requestFor = (fixtureName) => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture(fixtureName, cfg);
    const [gateOut] = gate(normalized, org);
    return clayRequest(gateOut.json)[0].json;
  };

  test('org_full -> domain, high confidence', () => {
    const out = requestFor('org_full.json');
    assert.equal(out.identifier_kind, 'domain');
    assert.equal(out.identifier_value, 'akuvo.com');
    assert.equal(out.identifier_confidence, 'high');
  });

  test('org_no_website -> linkedin, high confidence', () => {
    const out = requestFor('org_no_website.json');
    assert.equal(out.identifier_kind, 'linkedin');
    assert.equal(out.identifier_value, 'https://www.linkedin.com/company/qcash-financial');
    assert.equal(out.identifier_confidence, 'high');
  });

  test('org_no_identifiers -> name, LOW confidence', () => {
    const out = requestFor('org_no_identifiers.json');
    assert.equal(out.identifier_kind, 'name');
    assert.equal(out.identifier_value, 'stealth robotics');
    assert.equal(out.identifier_confidence, 'low');
  });

  test('a name-only org still carries the three fields find_by_name needs', () => {
    // The table's find_by_name step has nothing but these. If the body omitted
    // company_name the lookup could not run at all, and without the country and
    // state it would resolve the wrong company of the same name — which scores
    // a stranger's CRM record and looks exactly like a correct run.
    const out = requestFor('org_no_identifiers.json');
    assert.equal(out.identifier_kind, 'name');
    assert.ok(Object.prototype.hasOwnProperty.call(out.body, 'company_name'));
    assert.ok(Object.prototype.hasOwnProperty.call(out.body, 'hq_country'));
    assert.ok(Object.prototype.hasOwnProperty.call(out.body, 'hq_state'));
    assert.equal(typeof out.body.company_name, 'string');
    assert.ok(out.body.company_name.length > 0);
  });

  test('every enrichment key is present even when null — omission is not absence', () => {
    // Clay's facts_json must be able to tell "enrichment did not find it" from
    // "we never asked". An omitted key destroys that distinction, so the body
    // sends the full key set on every path.
    const KEYS = [
      'request_id', 'org_id', 'deal_id', 'requested_at',
      'identifier_kind', 'identifier_value',
      'domain', 'linkedin_url', 'company_name', 'hq_country', 'hq_state',
      'model_version', 'callback_url',
    ];
    for (const fixtureName of ['org_full.json', 'org_no_website.json', 'org_no_identifiers.json']) {
      const out = requestFor(fixtureName);
      assert.deepEqual(Object.keys(out.body).sort(), [...KEYS].sort(), fixtureName);
    }
  });

  test('the spliced normalizer agrees with engine/normalize.mjs', () => {
    for (const fixtureName of ['org_full.json', 'org_no_website.json', 'org_no_identifiers.json']) {
      const { org } = orgFixture(fixtureName, cfg);
      const expected = resolveIdentifier({
        name: org.name, website: org.website, linkedin: org.linkedin,
      });
      const out = requestFor(fixtureName);
      assert.equal(out.identifier_kind, expected.kind, fixtureName);
      assert.equal(out.identifier_value, expected.value, fixtureName);
      assert.equal(out.identifier_confidence, expected.confidence, fixtureName);
      assert.deepEqual(out.identifier_warnings, expected.warnings, fixtureName);
    }
  });

  test('a LinkedIn URL in the website field never becomes the domain', () => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture('org_full.json', cfg);
    org.website = 'https://www.linkedin.com/company/concertai';
    org.linkedin = null;
    const [gateOut] = gate(normalized, org);
    const out = clayRequest(gateOut.json)[0].json;
    assert.equal(out.identifier_kind, 'linkedin');
    assert.equal(out.body.domain, null, 'linkedin.com must not be sent as the domain');
    assert.equal(out.identifier_confidence, 'low');
  });

  test('nulls are SENT as null, never omitted — Clay needs the distinction', () => {
    const out = requestFor('org_no_identifiers.json');
    for (const key of ['domain', 'linkedin_url', 'hq_country', 'hq_state']) {
      assert.ok(key in out.body, `${key} must be present`);
      assert.equal(out.body[key], null);
    }
  });

  test('the callback URL comes from CONFIG, not from a literal', () => {
    const out = requestFor('org_full.json');
    assert.equal(out.body.callback_url, cfg.clay_callback_url);
    assert.equal(out.clay_url, cfg.clay_engine_url);
  });

  test('an org with nothing usable throws a typed error', () => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture('org_no_identifiers.json', cfg);
    org.name = '';
    const [gateOut] = gate(normalized, org);
    assert.throws(() => clayRequest(gateOut.json), /ICP_NO_IDENTIFIER/);
  });
});

// ==========================================================================
describe('ParseScored', () => {
  test('a valid event parses and flattens every component the same way', () => {
    const event = clayFixture('icp_scored_A.json');
    const [out] = parseScored(event);
    assert.equal(out.json._path, 'B');
    assert.equal(out.json.model_version, 'v6');
    assert.equal(out.json.requested_at, event.requested_at);
    assert.equal(out.json.org_id, 10001, 'ids stay numeric through the boundary');

    const c = out.json.components;
    assert.deepEqual(Object.keys(c).sort(), [
      'activation_state', 'buying_signal', 'company_type', 'geography',
      'industry_vertical', 'revenue_range', 'stage_maturity',
    ]);
    assert.equal(c.industry_vertical.value, 'FinTech', 'a value component keeps its value');
    assert.equal(c.company_type.value, 10, 'a levelled component exposes its level as value');
    assert.equal(c.revenue_range.revenue_source, 'headcount_band');
    assert.equal(c.activation_state.activation_evidence_dated, 'apollo.funding_events[0].date: 2025-09-01');
    // buying_signal states no confidence; absence is recorded as null, never
    // as "low" — there was no classifier to be unsure.
    assert.equal(c.buying_signal.confidence, null);
  });

  test('no score reaches ParseScored, and none leaves it', () => {
    const [out] = parseScored(clayFixture('icp_scored_A.json'));
    assert.equal(out.json.score, undefined, 'scoring is the Score node\'s job');
  });

  test('malformed -> a typed error naming every violation', () => {
    const event = clayFixture('icp_scored_malformed.json');
    assert.throws(() => parseScored(event), (error) => {
      assert.equal(error.name, 'IcpMalformedEvent');
      assert.match(error.message, /ICP_MALFORMED_EVENT/);
      assert.ok(error.problems.length >= 6, `expected >= 6 problems, got ${error.problems.length}`);
      assert.ok(error.problems.some((p) => /org_id must be a positive integer/.test(p)));
      assert.ok(error.problems.some((p) => /engineering_hiring\.eng_open is missing/.test(p)));
      assert.ok(error.problems.some((p) => /company_type\.level must be null or one of/.test(p)));
      assert.ok(error.problems.some((p) => /revenue_range\.confidence must be one of/.test(p)));
      assert.ok(error.problems.some((p) => /headcount_6mo_growth is missing/.test(p)));
      assert.ok(error.problems.some((p) => /unknown top-level key/.test(p)));
      return true;
    });
  });

  test('every fixture the schema accepts, ParseScored accepts', () => {
    for (const name of VALID_FIXTURES) {
      const [out] = parseScored(clayFixture(name));
      assert.equal(out.json._path, 'B', name);
    }
  });

  test('a wrong model version is rejected', () => {
    const event = clayFixture('icp_scored_A.json');
    event.model_version = 'v5';
    assert.throws(() => parseScored(event), /model_version must be "v6"/);
  });

  test('an off-ladder level is rejected', () => {
    const event = clayFixture('icp_scored_A.json');
    event.cls_all.geography.level = 5;
    assert.throws(() => parseScored(event), /cls_all\.geography\.level must be null or one of/);
  });
});

// ==========================================================================
describe('Score', () => {
  test('it runs the same arithmetic as engine/scoring.mjs, on every fixture', () => {
    for (const name of VALID_FIXTURES) {
      const out = scored(name);
      const event = clayFixture(name);
      const c = event.cls_all;
      const guard = activationStateFor(
        c.activation_state, event.apollo_summary, event.requested_at, cfg.activation_default
      );
      const conf = (x) => (x.confidence === undefined ? null : x.confidence);
      const miss = (x) => x.missing_inputs || [];
      const expected = score({
        industry_vertical: c.industry_vertical.value,
        levels: {
          stage_maturity: c.stage_maturity.level, company_type: c.company_type.level,
          geography: c.geography.level, revenue_range: c.revenue_range.level,
          buying_signal: c.buying_signal.level,
        },
        activation_state: guard.state,
        activation_evidence_dated_within_months: 0,
        confidence: {
          industry_vertical: conf(c.industry_vertical), stage_maturity: conf(c.stage_maturity),
          company_type: conf(c.company_type), geography: conf(c.geography),
          revenue_range: conf(c.revenue_range), buying_signal: conf(c.buying_signal),
        },
        missing_inputs: {
          industry_vertical: miss(c.industry_vertical), stage_maturity: miss(c.stage_maturity),
          company_type: miss(c.company_type), geography: miss(c.geography),
          revenue_range: miss(c.revenue_range), buying_signal: miss(c.buying_signal),
        },
        facts_summary: {
          revenue_usd: null,
          headcount_total: event.apollo_summary.employees,
          headcount_eng: event.apollo_summary.eng_headcount,
        },
      });
      assert.equal(out.score.composite, expected.composite, name);
      assert.equal(out.score.final_score, expected.final_score, name);
      assert.equal(out.score.final_score_without_activation, expected.final_score_without_activation, name);
      assert.equal(out.score.grade, expected.grade, name);
      assert.equal(out.score.status, expected.status, name);
      assert.equal(out.score.multiplier, expected.multiplier, name);
      assert.equal(out.score.tier2_candidate, expected.tier2_candidate, name);
      assert.equal(out.score.confidence_overall, expected.confidence_overall, name);
      assert.deepEqual(out.score.levels, {
        industries: expected.levels_used.industry,
        stage_maturity: expected.levels_used.stage_maturity,
        company_type: expected.levels_used.company_type,
        geography: expected.levels_used.geography,
        revenue_range: expected.levels_used.revenue_range,
        buying_signal: expected.levels_used.buying_signal,
      }, name);
    }
  });

  test('A: an accelerating fintech grades A', () => {
    const out = scored('icp_scored_A.json');
    assert.equal(out.score.grade, 'A');
    assert.equal(out.score.multiplier, 1);
    assert.equal(out.score.contracting_guard_applied, false);
  });

  test('B_stable: the composite clears 75 and x0.80 puts it in B', () => {
    const out = scored('icp_scored_B_stable.json');
    assert.ok(out.score.composite >= 75, `composite ${out.score.composite}`);
    assert.equal(out.score.multiplier, 0.8);
    assert.equal(out.score.grade, 'B');
    assert.ok(out.score.final_score_without_activation >= cfg.thresholds.A,
      'and the counterfactual says it would have been an A');
  });

  test('contracting_valid: a measured 18% fall backs Contracting, and zeroes it', () => {
    const out = scored('icp_scored_contracting_valid.json');
    assert.equal(out.score.activation_state_used, 'Contracting');
    assert.equal(out.score.contracting_guard_applied, false);
    assert.equal(out.score.multiplier, 0);
    assert.equal(out.score.final_score, 0);
    assert.ok(out.score.final_score_without_activation > 0, 'the counterfactual survives the zero');
  });

  test('contracting_unbacked: growth of +5% downgrades the claim and flags it', () => {
    const out = scored('icp_scored_contracting_unbacked.json');
    assert.equal(out.score.activation_state_claimed, 'Contracting');
    assert.equal(out.score.activation_state_used, 'Stable');
    assert.equal(out.score.contracting_guard_applied, true);
    assert.equal(out.score.multiplier, 0.8);
    assert.ok(out.score.flags.includes('contracting_without_dated_evidence'));
    assert.match(out.score.contracting_guard_reason, /0\.05 > -0\.15/);
    assert.notEqual(out.score.final_score, 0, 'an unbacked claim must not zero an account');
  });

  test('insufficient: a low-confidence stage with gaps yields no grade', () => {
    const out = scored('icp_scored_insufficient.json');
    assert.equal(out.score.status, 'insufficient_data');
    assert.equal(out.score.grade, null);
    assert.ok(out.score.flags.some((f) => f.startsWith('insufficient:')));
  });

  test('tier2: revenue level 0 with 71000 employees flags tier 2', () => {
    const out = scored('icp_scored_tier2.json');
    assert.equal(out.score.levels.revenue_range, 0);
    assert.ok(out.apollo_summary.employees > 1000);
    assert.equal(out.score.tier2_candidate, true);
    assert.ok(out.score.flags.includes('tier2_candidate'));
  });

  test('unknown_vertical: not in the v6 sub-rubric means level 0 and a flag', () => {
    const out = scored('icp_scored_unknown_vertical.json');
    assert.equal(out.components.industry_vertical.value, 'Horizontal B2B Software');
    assert.equal(out.score.levels.industries, 0);
    assert.ok(out.score.flags.includes('unknown_vertical'));
    // Industry carries 15 of 100, so a strong account can still grade well —
    // the flag is the signal, not the grade.
    assert.equal(out.score.industry_tier, null);
  });

  test('the guard runs before the scorer, so the flag is raised exactly once', () => {
    const out = scored('icp_scored_contracting_unbacked.json');
    const raised = out.score.flags.filter((f) => f === 'contracting_without_dated_evidence');
    assert.equal(raised.length, 1);
  });

  test('Score passes ParseScored\'s output through untouched', () => {
    const [parsed] = parseScored(clayFixture('icp_scored_A.json'));
    const out = scoreNode(parsed.json)[0].json;
    for (const key of Object.keys(parsed.json)) {
      assert.deepEqual(out[key], parsed.json[key], key);
    }
  });
});

// ==========================================================================
describe('BuildOrgPatch', () => {
  const patchFor = (eventName, orgName = 'org_full.json', mutate = null) => {
    const out0 = scored(eventName);
    const { org } = orgFixture(orgName, cfg);
    if (mutate) mutate(org, out0);
    return { out: orgPatch(out0, org)[0].json, parsed: out0, org };
  };

  test('scored A -> the patch carries 4 fields and the ICP A option id', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.equal(out.changed_fields.length, 4);
    assert.equal(Object.keys(out.patch.custom_fields).length, 4);
    assert.equal(out.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated['ICP A']);
    assert.equal(out.patch.custom_fields[cfg.f_icp_score], 93);
    assert.equal(out.patch.custom_fields[cfg.f_icp_scored_at], '2026-09-09');
    assert.equal(out.patch.custom_fields[cfg.f_icp_model_version], 'v6');
  });

  test('the enum is written by option id, never by label', () => {
    const { out } = patchFor('icp_scored_A.json');
    const written = out.patch.custom_fields[cfg.f_icp_calculated];
    assert.equal(typeof written, 'number');
    assert.notEqual(written, 'ICP A');
  });

  test('Stable crossing a threshold -> ICP B even though the composite clears 75', () => {
    const { out, parsed } = patchFor('icp_scored_B_stable.json');
    assert.ok(parsed.score.composite >= 75, `composite ${parsed.score.composite} must clear 75`);
    assert.ok(parsed.score.final_score < 75, `final ${parsed.score.final_score} must not`);
    assert.equal(out.target_label, 'ICP B');
    assert.equal(out.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated['ICP B']);
  });

  test('insufficient -> the Insufficient data option id, and no score written', () => {
    const { out } = patchFor('icp_scored_insufficient.json');
    assert.equal(out.target_label, 'Insufficient data');
    assert.equal(out.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated['Insufficient data']);
    // The org had no score, so there is nothing to clear and the key is
    // correctly absent — writing null to an already-empty field is a wasted
    // write, and the no-churn rule forbids it.
    assert.ok(
      !Object.prototype.hasOwnProperty.call(out.patch.custom_fields, cfg.f_icp_score),
      'no score key when the org had no score to clear'
    );
    assert.ok(!out.changed_fields.includes(cfg.f_icp_score));
  });

  test('insufficient CLEARS a previous score with null, rather than leaving it', () => {
    // This is the case that matters: a stale 93 sitting under an
    // "Insufficient data" label reads as a score of the wrong kind.
    const { out } = patchFor('icp_scored_insufficient.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_icp_score] = 93;
      org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated['ICP A'];
    });
    assert.ok(out.changed_fields.includes(cfg.f_icp_score));
    assert.equal(
      out.patch.custom_fields[cfg.f_icp_score], null,
      'Pipedrive clears a field with null, not with ""'
    );
    assert.equal(out.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated['Insufficient data']);
  });

  test('Contracting -> grade C', () => {
    const { out, parsed } = patchFor('icp_scored_contracting_valid.json');
    assert.equal(parsed.score.grade, 'C');
    assert.equal(out.target_label, 'ICP C');
  });

  test('tier2 -> grade C', () => {
    const { out, parsed } = patchFor('icp_scored_tier2.json');
    assert.equal(parsed.score.tier2_candidate, true);
    assert.equal(parsed.score.grade, 'C');
    assert.equal(out.target_label, 'ICP C');
  });

  test('no churn — identical values produce {} and the IF gate skips the PATCH', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated['ICP A'];
      org.custom_fields[cfg.f_icp_score] = 93;
      org.custom_fields[cfg.f_icp_scored_at] = '2026-09-09';
      org.custom_fields[cfg.f_icp_model_version] = 'v6';
    });
    assert.deepEqual(out.patch, {});
    assert.equal(out.patch_is_empty, true);
    assert.deepEqual(out.changed_fields, []);
    assert.equal(out.unchanged_fields.length, 4);
  });

  test('one differing field produces a patch of exactly that field', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated['ICP A'];
      org.custom_fields[cfg.f_icp_score] = 91; // stale score
      org.custom_fields[cfg.f_icp_scored_at] = '2026-09-09';
      org.custom_fields[cfg.f_icp_model_version] = 'v6';
    });
    assert.deepEqual(out.changed_fields, [cfg.f_icp_score]);
    assert.deepEqual(Object.keys(out.patch.custom_fields), [cfg.f_icp_score]);
  });

  test('never touches ICP Final — asserted on the CONFIG key', () => {
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting_valid.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const { out } = patchFor(name);
      const keys = Object.keys(out.patch.custom_fields || {});
      assert.ok(!keys.includes(cfg.f_icp_final), `${name} must not write ICP Final`);
      assert.ok(cfg.fields_never_write.includes(cfg.f_icp_final), 'and the guard must know about it');
    }
  });

  test('a pre-existing ICP Final is left exactly as it was', () => {
    const { out, org } = patchFor('icp_scored_A.json', 'org_full.json', (org2) => {
      org2.custom_fields[cfg.f_icp_final] = cfg.opt_icp_calculated['ICP C'];
    });
    assert.equal(org.custom_fields[cfg.f_icp_final], cfg.opt_icp_calculated['ICP C']);
    assert.ok(!Object.keys(out.patch.custom_fields).includes(cfg.f_icp_final));
  });

  test('a missing option id fails loudly rather than writing a label', () => {
    const broken = makeConfig({
      opt_icp_calculated: { 'ICP A': null, 'ICP B': 102, 'ICP C': 103, 'Insufficient data': 104, Error: 105 },
    });
    const out0 = scored('icp_scored_A.json');
    const { org } = orgFixture('org_full.json', broken);
    assert.throws(
      () => runCodeNode(SRC.BuildOrgPatch, { input: [org], nodes: { CONFIG: broken, Score: out0 } }),
      /ICP_MISSING_OPTION_ID/
    );
  });
});

// ==========================================================================
describe('BuildNote', () => {
  const noteFor = (name) => {
    const out = scored(name);
    return { note: buildNote(out)[0].json, parsed: out };
  };

  test('scored A -> 5 component lines, and every §8.3 line is present', () => {
    const { note } = noteFor('icp_scored_A.json');
    const lines = note.note.split('\n');
    assert.match(lines[0], /^ICP v6 — Calculated: ICP A \(93\/100\)$/);
    const componentLines = lines.filter((l) => /^(Industry|Stage|Type|Geography|Revenue) \d+ /.test(l));
    assert.equal(componentLines.length, 5, `expected 5 component lines, got:\n${note.note}`);
    assert.ok(lines.some((l) => l.startsWith('Activation:')));
    assert.ok(lines.some((l) => l.startsWith('Composite:')));
    assert.ok(lines.some((l) => l.startsWith('Reference:')));
    assert.ok(lines.some((l) => l.startsWith('Missing / low confidence:')));
  });

  test('the component lines read "<name> <level> <text> — <evidence>"', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.match(note.note, /^Industry 10 FinTech \(Anchor\) — li_industry: Financial Services/m);
    assert.match(note.note, /^Geography 10 US-based — apollo\.country: United States/m);
  });

  test('the Revenue line names where the band came from', () => {
    // A band inferred from headcount and a band read off a filing are not the
    // same claim, and the rep deciding whether to trust a B is the person who
    // needs to know which one this is.
    const { note } = noteFor('icp_scored_A.json');
    assert.match(note.note, /^Revenue 7 \$10M–\$25M via headcount_band \(apollo revenue \$1\.1M discarded: \$12k\/employee\)$/m);
    const stable = noteFor('icp_scored_B_stable.json');
    assert.match(stable.note.note, /^Revenue 7 \$10M–\$25M via apollo_revenue$/m);
  });

  test('the Hiring line distinguishes found, none found, and undated', () => {
    assert.match(noteFor('icp_scored_A.json').note.note,
      /^Hiring 3 eng open, 2 ≥60d, leader: Head of Engineering, ratio 0\.17$/m);
    assert.match(noteFor('icp_scored_insufficient.json').note.note,
      /^Hiring no postings found$/m);

    const undated = clayFixture('icp_scored_A.json');
    undated.cls_all.engineering_hiring.dates_available = false;
    const out = buildNote(scored(undated))[0].json;
    assert.match(out.note, /^Hiring 3 eng open, dates unavailable$/m);
  });

  test('the level text is the rubric text, from config', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.ok(note.note.includes(cfg.component_scales.geography['10']));
    assert.ok(note.note.includes(cfg.component_scales.stage_maturity['10']));
  });

  test('the Reference line carries HC, eng HC and the buying signal', () => {
    const { note } = noteFor('icp_scored_A.json');
    const line = note.note.split('\n').find((l) => l.startsWith('Reference:'));
    assert.match(line, /HC 91 · eng HC 18 · buying signal 7/);
  });

  test('an unknown headcount reads n/a, never 0', () => {
    const { note } = noteFor('icp_scored_insufficient.json');
    const line = note.note.split('\n').find((l) => l.startsWith('Reference:'));
    assert.match(line, /HC n\/a · eng HC n\/a/);
  });

  test('a conflict the table reported gets its own line', () => {
    const { note } = noteFor('icp_scored_contracting_valid.json');
    assert.match(note.note, /^Conflict: headcount fell 18% in six months while the funding stage still reads Series C$/m);
  });

  test('an unbacked Contracting says on the note why it was downgraded', () => {
    const { note } = noteFor('icp_scored_contracting_unbacked.json');
    assert.match(note.note, /Activation: Stable ×0\.80 .* Contracting claimed but not backed \(/);
    assert.match(note.note, /downgraded to Stable/);
  });

  test('the counterfactual is shown whenever the multiplier is not 1.00', () => {
    // A discounted score is illegible without it: "68" means nothing until you
    // can see it was 85 before activation.
    for (const name of ['icp_scored_B_stable.json', 'icp_scored_contracting_valid.json', 'icp_scored_tier2.json']) {
      const { note } = noteFor(name);
      assert.match(note.note, /without activation: \d+ → ICP [ABC]/, name);
    }
    // And not shown when it would be noise.
    assert.doesNotMatch(noteFor('icp_scored_A.json').note.note, /without activation/);
  });

  test('a computed component contributes nothing to the Missing line', () => {
    // geography, revenue_range and buying_signal have no classifier in v6, so
    // they have no confidence either. Reading that absence as "low confidence"
    // would put three components on the Missing line of every single note.
    const { note } = noteFor('icp_scored_A.json');
    const missing = note.note.split('\n').find((l) => l.startsWith('Missing / low confidence:'));
    assert.doesNotMatch(missing, /geography/);
    assert.doesNotMatch(missing, /buying_signal/);
  });

  test('Stable shows the ×0.80 that cost the grade', () => {
    const { note } = noteFor('icp_scored_B_stable.json');
    assert.match(note.note, /Activation: Stable ×0\.80/);
    assert.match(note.note, /Composite: 92\.5 ×0\.80 → 74 → ICP B/);
  });

  test('Contracting shows the counterfactual', () => {
    const { note } = noteFor('icp_scored_contracting_valid.json');
    assert.match(note.note, /without activation: 93 → ICP A/);
    assert.match(note.note, /Activation: Contracting ×0\.00/);
  });

  test('insufficient_data reads "Insufficient data" and the Missing line is non-empty', () => {
    const { note } = noteFor('icp_scored_insufficient.json');
    assert.match(note.note, /^ICP v6 — Calculated: Insufficient data$/m);
    assert.ok(!/\(\d+\/100\)/.test(note.note.split('\n')[0]), 'no score in the header');
    const missing = note.note.split('\n').find((l) => l.startsWith('Missing / low confidence:'));
    assert.ok(missing, 'the Missing line is mandatory');
    const payload = missing.replace('Missing / low confidence:', '').trim();
    assert.ok(payload.length > 0, 'and non-empty');
    assert.match(payload, /revenue_range/);
    assert.match(payload, /stage_maturity/);
  });

  test('a Tier 2 candidate says so', () => {
    const { note } = noteFor('icp_scored_tier2.json');
    assert.match(note.note, /Tier 2 candidate/);
  });

  test('every note fits the character budget', () => {
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting_valid.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const { note } = noteFor(name);
      assert.ok(note.note_length <= cfg.note_max_chars, `${name}: ${note.note_length} chars`);
    }
  });

  test('a pathological evidence string is trimmed deterministically, not truncated raggedly', () => {
    const event = clayFixture('icp_scored_A.json');
    for (const component of ['industry_vertical', 'company_type', 'stage_maturity', 'activation_state', 'geography', 'revenue_range']) {
      event.cls_all[component].evidence = [
        `li_description: ${'x'.repeat(190)}`, `website_summary: ${'y'.repeat(190)}`,
      ];
    }
    const out = scored(event);
    const first = buildNote(out)[0].json;
    const second = buildNote(out)[0].json;
    assert.ok(first.note_length <= cfg.note_max_chars);
    assert.equal(first.note, second.note, 'the same input must yield the same note');
    assert.ok(first.note.split('\n').some((l) => l.startsWith('Missing / low confidence:')));
  });

  test('the footer carries request_id and the model version', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.match(note.note, /request_id req-icp-0001 · model v6 · 2026-09-09/);
  });

  test('there is no score in the event for the note to disagree with', () => {
    // v5 carried Clay's score and stamped CLAY SCORE DRIFT when n8n's recompute
    // differed. v6 has one implementation of the rubric in the delivery path,
    // so there is no second number and no drift banner to look for.
    const { note } = noteFor('icp_scored_A.json');
    assert.doesNotMatch(note.note, /DRIFT/);
  });
});

// ==========================================================================
describe('BuildAuditRow', () => {
  const EXPECTED_COLUMNS = [
    'ts', 'requested_at', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
    'identifier_kind', 'identifier_value', 'model_version',
    'industry_vertical', 'industry_level', 'stage_level', 'type_level',
    'geo_level', 'revenue_level', 'revenue_source', 'buying_level',
    'eng_open', 'eng_open_60d_plus',
    'activation_state', 'contracting_guard_applied', 'multiplier', 'composite', 'final',
    'final_without_activation', 'grade', 'status', 'confidence_overall',
    'tier2_candidate', 'flags', 'missing_inputs', 'evidence_json',
    'patch_written', 'note_id', 'error',
  ];

  test('the table spec and the node agree on the column set', () => {
    // The Data Table node maps by NAME. A column in one list and not the other
    // is a value that vanishes on write with no error anywhere — so the two
    // lists are compared here rather than being kept in step by hand.
    const spec = JSON.parse(
      readFileSync(join(ROOT, 'config', 'icp_audit_table.json'), 'utf8')
    );
    assert.deepEqual(spec.columns.map((c) => c.name), EXPECTED_COLUMNS);
    const TYPES = new Set(['string', 'number', 'boolean', 'date']);
    for (const column of spec.columns) {
      assert.ok(TYPES.has(column.type), `${column.name}: n8n Data Tables have no "${column.type}" type`);
    }
  });

  test('every emitted value fits the type its column declares', () => {
    const spec = JSON.parse(
      readFileSync(join(ROOT, 'config', 'icp_audit_table.json'), 'utf8')
    );
    const typeOf = new Map(spec.columns.map((c) => [c.name, c.type]));
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting_valid.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const [row] = auditRow(scored(name));
      for (const [key, value] of Object.entries(row.json)) {
        const expected = typeOf.get(key);
        if (expected === 'number') assert.equal(typeof value, 'number', `${name} / ${key} = ${JSON.stringify(value)}`);
        else if (expected === 'boolean') assert.equal(typeof value, 'boolean', `${name} / ${key}`);
        else assert.equal(typeof value, 'string', `${name} / ${key} = ${JSON.stringify(value)}`);
      }
    }
  });

  test('the row has the §8.4 columns, in the §8.4 order', () => {
    const out = scored('icp_scored_A.json');
    const [row] = auditRow(out);
    assert.deepEqual(Object.keys(row.json), EXPECTED_COLUMNS);
    assert.equal(EXPECTED_COLUMNS.length, 36);
  });

  test('a scored run fills the score columns', () => {
    const out0 = scored('icp_scored_A.json');
    const { org } = orgFixture('org_full.json', cfg);
    const patch = orgPatch(out0, org)[0].json;
    const note = buildNote(out0)[0].json;
    const [row] = auditRow(out0, {
      BuildOrgPatch: patch, BuildNote: note, 'POST note': { data: { id: 7788 } },
    });
    const r = row.json;
    assert.equal(r.request_id, 'req-icp-0001');
    assert.equal(r.trigger, 'clay.icp.scored');
    assert.equal(r.industry_vertical, 'FinTech');
    assert.equal(r.industry_level, 10);
    assert.equal(r.grade, 'A');
    assert.equal(r.status, 'scored');
    assert.equal(r.multiplier, 1);
    assert.equal(r.composite, 92.5);
    assert.equal(r.final, 93);
    assert.equal(r.patch_written, true);
    assert.equal(r.note_id, '7788');
    assert.equal(r.error, '');
    assert.equal(r.execution_id, 'exec-test-0001');
  });

  test('a duplicate is flagged and patch_written is false', () => {
    const staticData = {};
    const event = clayFixture('icp_scored_A.json');
    scored(event, staticData);
    const out0 = scored(event, staticData);
    assert.equal(out0._duplicate, true);
    const [row] = auditRow(out0);
    assert.match(row.json.error, /duplicate/);
    assert.equal(row.json.patch_written, false);
    assert.equal(row.json.note_id, '');
  });

  test('evidence_json covers the four classifiers and only those', () => {
    const out = scored('icp_scored_A.json');
    const [row] = auditRow(out);
    const evidence = JSON.parse(row.json.evidence_json);
    // v6 gives every component evidence, including the three the table levels
    // itself, so all seven are recorded.
    assert.deepEqual(Object.keys(evidence).sort(), [
      'activation_state', 'buying_signal', 'company_type', 'geography',
      'industry_vertical', 'revenue_range', 'stage_maturity',
    ]);
    assert.ok(Array.isArray(evidence.industry_vertical));
    assert.ok(evidence.geography.length > 0);
  });

  test('missing_inputs is recorded per classifier', () => {
    const out = scored('icp_scored_insufficient.json');
    const [row] = auditRow(out);
    assert.match(row.json.missing_inputs, /stage_maturity:funding_stage/);
    assert.equal(row.json.grade, '', 'no grade on insufficient data');
    assert.equal(row.json.status, 'insufficient_data');
    // revenue_range is the component that made this insufficient, and in v6 it
    // has no classifier to report a gap. The flag is where that survives.
    assert.match(row.json.flags, /insufficient:[^|]*revenue_range/);
  });

  test("the table's conflict note is recorded in the error column", () => {
    // v5 used this column for a score drift between Clay and n8n's recompute.
    // v6 rejects a disagreeing score outright, so what lands here instead is
    // the conflict the table itself reported — something that explains a score
    // rather than contradicting it.
    const out = scored('icp_scored_contracting_valid.json');
    const [row] = auditRow(out);
    assert.match(row.json.error, /^conflict:headcount fell 18%/);
  });

  test('the five v6 columns carry what they say', () => {
    const [row] = auditRow(scored('icp_scored_A.json'));
    assert.equal(row.json.requested_at, '2026-09-18T10:42:00Z');
    assert.equal(row.json.revenue_source, 'headcount_band');
    assert.equal(row.json.eng_open, 3);
    assert.equal(row.json.eng_open_60d_plus, 2);
    assert.equal(row.json.contracting_guard_applied, false);
    assert.equal(auditRow(scored('icp_scored_contracting_unbacked.json'))[0].json.contracting_guard_applied, true);
  });

  test('an absent hiring count is -1, not 0', () => {
    // A number column cannot hold "unknown" and 0 would be a lie: the provider
    // returning nothing and a company having nothing open are opposite facts.
    const [row] = auditRow(scored('icp_scored_insufficient.json'));
    assert.equal(row.json.eng_open, -1);
    assert.equal(row.json.eng_open_60d_plus, -1);
    assert.equal(auditRow(scored('icp_scored_contracting_valid.json'))[0].json.eng_open, 0,
      'and a real zero is still a zero');
  });
});

// ==========================================================================
describe('BuildErrorPatch', () => {
  test('a malformed event ends up marked Error', () => {
    const event = clayFixture('icp_scored_malformed.json');
    let thrown;
    try { parseScored(event); } catch (error) { thrown = error; }
    assert.ok(thrown, 'ParseScored must throw');

    // n8n hands the error branch the failing item plus an `error` property.
    const { org } = orgFixture('org_full.json', cfg);
    const [out] = runCodeNode(SRC.BuildErrorPatch, {
      input: [{
        request_id: event.request_id, org_id: event.org_id, deal_id: event.deal_id,
        organization: org,
        error: { name: thrown.name, message: thrown.message },
      }],
      nodes: { CONFIG: cfg },
    });
    assert.equal(out.json.target_label, 'Error');
    assert.equal(out.json.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated.Error);
    assert.equal(out.json.error_name, 'IcpMalformedEvent');
    assert.match(out.json.error_message, /ICP_MALFORMED_EVENT/);
  });

  test('it is idempotent — an org already marked Error yields {}', () => {
    const { org } = orgFixture('org_full.json', cfg);
    org.custom_fields[cfg.f_icp_calculated] = cfg.opt_icp_calculated.Error;
    org.custom_fields[cfg.f_icp_scored_at] = '2026-09-09';
    org.custom_fields[cfg.f_icp_model_version] = 'v6';
    const [out] = runCodeNode(SRC.BuildErrorPatch, {
      input: [{ org_id: '10001', organization: org, error: { name: 'X', message: 'y' } }],
      nodes: { CONFIG: cfg },
    });
    assert.deepEqual(out.json.patch, {});
    assert.equal(out.json.patch_is_empty, true);
  });

  test('it records the date and model version so the gate does not retry forever', () => {
    const { org } = orgFixture('org_full.json', cfg);
    const [out] = runCodeNode(SRC.BuildErrorPatch, {
      input: [{ org_id: '10001', organization: org, error: { name: 'X', message: 'y' } }],
      nodes: { CONFIG: cfg },
    });
    assert.equal(out.json.patch.custom_fields[cfg.f_icp_scored_at], '2026-09-09');
    assert.equal(out.json.patch.custom_fields[cfg.f_icp_model_version], 'v6');
  });

  test('it never writes ICP Final', () => {
    const { org } = orgFixture('org_full.json', cfg);
    const [out] = runCodeNode(SRC.BuildErrorPatch, {
      input: [{ org_id: '10001', organization: org, error: { name: 'X', message: 'y' } }],
      nodes: { CONFIG: cfg },
    });
    assert.ok(!Object.keys(out.json.patch.custom_fields).includes(cfg.f_icp_final));
  });

  test('it degrades instead of throwing when the Error option id is missing', () => {
    // This node is the last line of the error path. Throwing here would lose
    // the Slack alert as well as the mark.
    const broken = makeConfig({
      opt_icp_calculated: { 'ICP A': 101, 'ICP B': 102, 'ICP C': 103, 'Insufficient data': 104, Error: null },
    });
    const [out] = runCodeNode(SRC.BuildErrorPatch, {
      input: [{ org_id: '10001', error: { name: 'X', message: 'y' } }],
      nodes: { CONFIG: broken },
    });
    assert.deepEqual(out.json.patch, {});
    assert.match(out.json.degraded, /no option id for "Error"/);
  });

  test('it survives an almost-empty item', () => {
    const [out] = runCodeNode(SRC.BuildErrorPatch, { input: [{}], nodes: { CONFIG: cfg } });
    assert.equal(out.json.org_id, null);
    assert.equal(out.json.error_name, 'IcpUnknownError');
    assert.equal(out.json.execution_id, 'exec-test-0001');
  });
});
