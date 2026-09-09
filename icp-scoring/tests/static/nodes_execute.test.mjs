// tests/static/nodes_execute.test.mjs — the §9.4 case table, run against the
// REAL Code-node sources with a mocked n8n scope.
//
// Every case here is a behaviour someone could remove. If a case can be
// deleted from a node without a test going red, the test is decoration.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  runCodeNode, readNode, makeConfig, orgFixture, clayFixture, pipedriveFixture, NOW_ISO,
} from './harness.mjs';
import { score } from '../../engine/scoring.mjs';
import { resolveIdentifier } from '../../engine/normalize.mjs';

const SRC = {
  Dedupe: readNode('Dedupe'),
  Normalize: readNode('Normalize'),
  IdempotencyGate: readNode('IdempotencyGate'),
  BuildClayRequest: readNode('BuildClayRequest'),
  ParseScored: readNode('ParseScored'),
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

const orgPatch = (parsed, org) => runCodeNode(SRC.BuildOrgPatch, {
  input: [org],
  nodes: { CONFIG: cfg, ParseScored: parsed },
});

const buildNote = (parsed) => runCodeNode(SRC.BuildNote, {
  nodes: { CONFIG: cfg, ParseScored: parsed },
});

const auditRow = (parsed, extra = {}) => runCodeNode(SRC.BuildAuditRow, {
  nodes: { CONFIG: cfg, ParseScored: parsed, ...extra },
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
    assert.equal(second[0].json._dedupe_key, 'clay:scored:req-icp-0001:clay-evt-a1b2c3d4e5f6');
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

  test('a Clay callback missing request_id or event_id throws rather than poisoning the ledger', () => {
    for (const missing of ['request_id', 'event_id']) {
      const event = clayFixture('icp_scored_A.json');
      delete event[missing];
      assert.throws(() => dedupeB(event, {}), /ICP_MALFORMED_EVENT/, missing);
    }
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

  test('old model (v4) inside the window -> skip false', () => {
    const { org } = orgFixture('org_scored_old_model.json', cfg);
    const [out] = gate(normalized(), org);
    assert.equal(out.json.skip, false, 'a date-only gate would wrongly skip this');
    assert.match(out.json.reason, /model version "v4"/);
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
    assert.equal(out.clay_url, cfg.clay_webhook_url);
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
  test('a valid event parses and the recompute agrees with the engine', () => {
    const event = clayFixture('icp_scored_A.json');
    const [out] = parseScored(event);
    assert.deepEqual(out.json.score_drift, [], 'n8n and Clay must agree');
    assert.equal(out.json.score.grade, 'A');
    assert.equal(out.json.score.final_score, event.score.final_score);
  });

  test('malformed -> a typed error naming every violation', () => {
    const event = clayFixture('icp_scored_malformed.json');
    assert.throws(() => parseScored(event), (error) => {
      assert.equal(error.name, 'IcpMalformedEvent');
      assert.match(error.message, /ICP_MALFORMED_EVENT/);
      assert.ok(error.problems.length >= 4, `expected >= 4 problems, got ${error.problems.length}`);
      assert.ok(error.problems.some((p) => /geography is missing/.test(p)));
      assert.ok(error.problems.some((p) => /final_score/.test(p)));
      assert.ok(error.problems.some((p) => /multiplier/.test(p)));
      assert.ok(error.problems.some((p) => /unknown top-level key/.test(p)));
      return true;
    });
  });

  test('every fixture the schema accepts, ParseScored accepts', () => {
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const [out] = parseScored(clayFixture(name));
      assert.deepEqual(out.json.score_drift, [], name);
    }
  });

  test('a wrong model version is rejected', () => {
    const event = clayFixture('icp_scored_A.json');
    event.model_version = 'v4';
    assert.throws(() => parseScored(event), /model_version must be "v5"/);
  });

  test('a vertical outside the 17 is rejected', () => {
    const event = clayFixture('icp_scored_A.json');
    event.components.industry_vertical.value = 'Crypto Casinos';
    assert.throws(() => parseScored(event), /not one of the 17 rubric verticals/);
  });

  test('an off-ladder level is rejected', () => {
    const event = clayFixture('icp_scored_A.json');
    event.components.geography.value = 5;
    assert.throws(() => parseScored(event), /is not one of \[0,3,7,10\]/);
  });

  test('the drift guard fires when Clay disagrees, and the tested value wins', () => {
    const event = clayFixture('icp_scored_A.json');
    event.score.final_score = 61;      // Clay says 61
    event.score.grade = 'B';
    const [out] = parseScored(event);
    assert.ok(out.json.score_drift.length > 0, 'the disagreement must be reported');
    assert.ok(out.json.score_drift.some((d) => d.startsWith('final_score:')));
    assert.equal(out.json.score.final_score, 93, 'the tested recompute wins');
    assert.equal(out.json.score.grade, 'A');
    assert.ok(out.json.score.flags.includes('clay_score_drift'));
    assert.equal(out.json.clay_score.final_score, 61, 'and Clay\'s value is kept for the audit row');
  });

  test('the recompute matches engine/scoring.mjs exactly, on every fixture', () => {
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const event = clayFixture(name);
      const [out] = parseScored(event);
      const c = event.components;
      const expected = score({
        industry_vertical: c.industry_vertical.value,
        levels: {
          stage_maturity: c.stage_maturity.value, company_type: c.company_type.value,
          geography: c.geography.value, revenue_range: c.revenue_range.value,
          buying_signal: c.buying_signal.value,
        },
        activation_state: c.activation_state.value,
        activation_evidence_dated_within_months: c.activation_state.evidence_dated_within_months ?? null,
        confidence: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.confidence])),
        missing_inputs: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.missing_inputs])),
        facts_summary: event.facts_summary,
      });
      assert.deepEqual(out.json.score, expected, name);
    }
  });
});

// ==========================================================================
describe('BuildOrgPatch', () => {
  const patchFor = (eventName, orgName = 'org_full.json', mutate = null) => {
    const [parsed] = parseScored(clayFixture(eventName));
    const { org } = orgFixture(orgName, cfg);
    if (mutate) mutate(org, parsed.json);
    return { out: orgPatch(parsed.json, org)[0].json, parsed: parsed.json, org };
  };

  test('scored A -> the patch carries 4 fields and the ICP A option id', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.equal(out.changed_fields.length, 4);
    assert.equal(Object.keys(out.patch.custom_fields).length, 4);
    assert.equal(out.patch.custom_fields[cfg.f_icp_calculated], cfg.opt_icp_calculated['ICP A']);
    assert.equal(out.patch.custom_fields[cfg.f_icp_score], 93);
    assert.equal(out.patch.custom_fields[cfg.f_icp_scored_at], '2026-09-09');
    assert.equal(out.patch.custom_fields[cfg.f_icp_model_version], 'v5');
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
    const { out, parsed } = patchFor('icp_scored_contracting.json');
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
      org.custom_fields[cfg.f_icp_model_version] = 'v5';
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
      org.custom_fields[cfg.f_icp_model_version] = 'v5';
    });
    assert.deepEqual(out.changed_fields, [cfg.f_icp_score]);
    assert.deepEqual(Object.keys(out.patch.custom_fields), [cfg.f_icp_score]);
  });

  test('never touches ICP Final — asserted on the CONFIG key', () => {
    for (const name of [
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting.json',
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
    const [parsed] = parseScored(clayFixture('icp_scored_A.json'));
    const { org } = orgFixture('org_full.json', broken);
    assert.throws(
      () => runCodeNode(SRC.BuildOrgPatch, { input: [org], nodes: { CONFIG: broken, ParseScored: parsed.json } }),
      /ICP_MISSING_OPTION_ID/
    );
  });
});

// ==========================================================================
describe('BuildNote', () => {
  const noteFor = (name) => {
    const [parsed] = parseScored(clayFixture(name));
    return { note: buildNote(parsed.json)[0].json, parsed: parsed.json };
  };

  test('scored A -> 5 component lines, and every §8.3 line is present', () => {
    const { note } = noteFor('icp_scored_A.json');
    const lines = note.note.split('\n');
    assert.match(lines[0], /^ICP v5 — Calculated: ICP A \(93\/100\)$/);
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
    assert.match(note.note, /^Geography 10 US-based — hq_country: United States/m);
  });

  test('the level text is the rubric text, from config', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.ok(note.note.includes(cfg.component_scales.geography['10']));
    assert.ok(note.note.includes(cfg.component_scales.revenue_range['7']));
  });

  test('the Reference line carries HC, eng HC and the buying signal', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.match(note.note, /^Reference: HC 190 · eng HC 62 · buying signal 7$/m);
  });

  test('Stable shows the ×0.85 that cost the grade', () => {
    const { note } = noteFor('icp_scored_B_stable.json');
    assert.match(note.note, /Activation: Stable ×0\.85/);
    assert.match(note.note, /Composite: 85 ×0\.85 → 72 → ICP B/);
  });

  test('Contracting shows the counterfactual', () => {
    const { note } = noteFor('icp_scored_contracting.json');
    assert.match(note.note, /without activation: 93 → ICP A/);
    assert.match(note.note, /Activation: Contracting ×0\.00/);
  });

  test('insufficient_data reads "Insufficient data" and the Missing line is non-empty', () => {
    const { note } = noteFor('icp_scored_insufficient.json');
    assert.match(note.note, /^ICP v5 — Calculated: Insufficient data$/m);
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
      'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting.json',
      'icp_scored_insufficient.json', 'icp_scored_tier2.json',
    ]) {
      const { note } = noteFor(name);
      assert.ok(note.note_length <= cfg.note_max_chars, `${name}: ${note.note_length} chars`);
    }
  });

  test('a pathological evidence string is trimmed deterministically, not truncated raggedly', () => {
    const event = clayFixture('icp_scored_A.json');
    for (const component of Object.keys(event.components)) {
      event.components[component].evidence = [
        `li_description: ${'x'.repeat(190)}`, `website_summary: ${'y'.repeat(190)}`,
      ];
    }
    const [parsed] = parseScored(event);
    const first = buildNote(parsed.json)[0].json;
    const second = buildNote(parsed.json)[0].json;
    assert.ok(first.note_length <= cfg.note_max_chars);
    assert.equal(first.note, second.note, 'the same input must yield the same note');
    assert.ok(first.note.split('\n').some((l) => l.startsWith('Missing / low confidence:')));
  });

  test('the footer carries request_id and the model version', () => {
    const { note } = noteFor('icp_scored_A.json');
    assert.match(note.note, /request_id req-icp-0001 · model v5 · 2026-09-09/);
  });

  test('a Clay drift is surfaced in the note, not only in the audit row', () => {
    const event = clayFixture('icp_scored_A.json');
    event.score.final_score = 61;
    event.score.grade = 'B';
    const [parsed] = parseScored(event);
    const note = buildNote(parsed.json)[0].json;
    assert.match(note.note, /CLAY SCORE DRIFT/);
  });
});

// ==========================================================================
describe('BuildAuditRow', () => {
  const EXPECTED_COLUMNS = [
    'ts', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
    'identifier_kind', 'identifier_value', 'model_version',
    'industry_vertical', 'industry_level', 'stage_level', 'type_level',
    'geo_level', 'revenue_level', 'buying_level',
    'activation_state', 'multiplier', 'composite', 'final',
    'final_without_activation', 'grade', 'status', 'confidence_overall',
    'tier2_candidate', 'flags', 'missing_inputs', 'evidence_json',
    'patch_written', 'note_id', 'error',
  ];

  test('the row has the §8.4 columns, in the §8.4 order', () => {
    const [parsed] = parseScored(clayFixture('icp_scored_A.json'));
    const [row] = auditRow(parsed.json);
    assert.deepEqual(Object.keys(row.json), EXPECTED_COLUMNS);
    assert.equal(EXPECTED_COLUMNS.length, 31);
  });

  test('a scored run fills the score columns', () => {
    const [parsed] = parseScored(clayFixture('icp_scored_A.json'));
    const { org } = orgFixture('org_full.json', cfg);
    const patch = orgPatch(parsed.json, org)[0].json;
    const note = buildNote(parsed.json)[0].json;
    const [row] = auditRow(parsed.json, {
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
    parseScored(event, staticData);
    const [parsed] = parseScored(event, staticData);
    assert.equal(parsed.json._duplicate, true);
    const [row] = auditRow(parsed.json);
    assert.match(row.json.error, /duplicate/);
    assert.equal(row.json.patch_written, false);
    assert.equal(row.json.note_id, '');
  });

  test('evidence_json is parseable and covers all seven components', () => {
    const [parsed] = parseScored(clayFixture('icp_scored_A.json'));
    const [row] = auditRow(parsed.json);
    const evidence = JSON.parse(row.json.evidence_json);
    assert.equal(Object.keys(evidence).length, 7);
    assert.ok(Array.isArray(evidence.industry_vertical));
  });

  test('missing_inputs is recorded per component', () => {
    const [parsed] = parseScored(clayFixture('icp_scored_insufficient.json'));
    const [row] = auditRow(parsed.json);
    assert.match(row.json.missing_inputs, /revenue_range:revenue_estimate_usd/);
    assert.equal(row.json.grade, '', 'no grade on insufficient data');
    assert.equal(row.json.status, 'insufficient_data');
  });

  test('a Clay drift is recorded in the error column', () => {
    const event = clayFixture('icp_scored_A.json');
    event.score.composite = 10;
    const [parsed] = parseScored(event);
    const [row] = auditRow(parsed.json);
    assert.match(row.json.error, /clay_score_drift/);
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
    org.custom_fields[cfg.f_icp_model_version] = 'v5';
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
    assert.equal(out.json.patch.custom_fields[cfg.f_icp_model_version], 'v5');
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
