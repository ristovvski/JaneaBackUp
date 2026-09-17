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
import { normalizeDomain } from '../../engine/normalize.mjs';
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
  BuildNoWebsiteWrite: readNode('BuildNoWebsiteWrite'),
  ParseScored: readNode('ParseScored'),
  Score: readNode('Score'),
  BuildOrgPatch: readNode('BuildOrgPatch'),
  BuildActivity: readNode('BuildActivity'),
  BuildRunSummary: readNode('BuildRunSummary'),
  BuildErrorContext: readNode('BuildErrorContext'),
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

const buildActivity = (out) => runCodeNode(SRC.BuildActivity, {
  nodes: { CONFIG: cfg, Score: out },
});

const runSummary = (out, extra = {}) => runCodeNode(SRC.BuildRunSummary, {
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
  const TODAY = String(NOW_ISO).slice(0, 10);
  const daysAgo = (n) => new Date(Date.parse(`${TODAY}T00:00:00Z`) - n * 86400000).toISOString().slice(0, 10);

  const gateWith = (autoScore, scoredAt, config = cfg) => {
    const { org } = orgFixture('org_full.json', config);
    if (autoScore === null) delete org.custom_fields[config.f_auto_icp_score];
    else org.custom_fields[config.f_auto_icp_score] = autoScore;
    if (scoredAt === null) delete org.custom_fields[config.f_auto_icp_scored_at];
    else org.custom_fields[config.f_auto_icp_scored_at] = scoredAt;
    return runCodeNode(SRC.IdempotencyGate, {
      input: [org], nodes: { CONFIG: config, Normalize: normalized() },
    })[0].json;
  };

  test('all three conditions met -> skip', () => {
    const out = gateWith('93 - A', daysAgo(10));
    assert.equal(out.skip, true);
    assert.match(out.reason, /fresh: "93 - A" scored 10d ago/);
    assert.equal(out.existing.age_days, 10);
    assert.equal(out.existing.on_current_model, true);
  });

  test('never scored -> re-score', () => {
    const out = gateWith(null, null);
    assert.equal(out.skip, false);
    assert.equal(out.reason, 'never scored');
  });

  test('a grade with no date -> re-score, because nothing can age it out', () => {
    const out = gateWith('93 - A', null);
    assert.equal(out.skip, false);
    assert.match(out.reason, /no usable Auto-ICP Scored At date/);
  });

  test('past the window -> re-score', () => {
    const out = gateWith('93 - A', daysAgo(200));
    assert.equal(out.skip, false);
    assert.match(out.reason, /stale: scored 200d ago \(>= 180d\)/);
  });

  test('exactly at the boundary is stale, not fresh', () => {
    assert.equal(gateWith('93 - A', daysAgo(cfg.rescore_after_days)).skip, false);
    assert.equal(gateWith('93 - A', daysAgo(cfg.rescore_after_days - 1)).skip, true);
  });

  test('scored before the current model took effect -> re-score', () => {
    // This is how "has the rubric changed?" is answered with a date field:
    // nothing on the organization stores a model version any more.
    const config = { ...cfg, model_effective_date: daysAgo(30) };
    assert.equal(gateWith('93 - A', daysAgo(60), config).skip, false, 'scored under the old rubric');
    const out = gateWith('93 - A', daysAgo(60), config);
    assert.match(out.reason, /before the .* model took effect/);
    assert.equal(gateWith('93 - A', daysAgo(10), config).skip, true, 'scored under the current one');
  });

  test('the day a rubric ships counts as on it, not before it', () => {
    const config = { ...cfg, model_effective_date: daysAgo(30) };
    assert.equal(gateWith('93 - A', daysAgo(30), config).skip, true);
    assert.equal(gateWith('93 - A', daysAgo(31), config).skip, false);
  });

  test('"n/a - insufficient data" always retries, however fresh', () => {
    // A run that found too little must not freeze the account out for six
    // months. This is the deviation on record, and it is why the gate looks at
    // the SHAPE of the value rather than at its presence.
    const out = gateWith('n/a - insufficient data', daysAgo(1));
    assert.equal(out.skip, false);
    assert.match(out.reason, /is not a grade — re-scoring/);
  });

  test('"n/a - error" always retries too', () => {
    assert.equal(gateWith('n/a - error', daysAgo(1)).skip, false);
  });

  test('a garbled value is not mistaken for a grade', () => {
    for (const value of ['A', '93', '93 -', 'ICP A', '93 - D', '993 - A - B']) {
      assert.equal(gateWith(value, daysAgo(1)).skip, false, value);
    }
  });

  test('the shape it accepts is tolerant of spacing, and nothing else', () => {
    for (const value of ['93 - A', '93-A', ' 7 -  B ', '0 - C']) {
      assert.equal(gateWith(value, daysAgo(1)).skip, true, value);
    }
  });

  test('a garbled date re-scores rather than skipping', () => {
    for (const value of ['not a date', '17/09/2026', '']) {
      assert.equal(gateWith('93 - A', value).skip, false, value);
    }
  });

  test('the literal reading is one CONFIG flag away', () => {
    const strict = { ...cfg, rescore_on_error_or_insufficient: false };
    assert.equal(gateWith('n/a - insufficient data', daysAgo(1), strict).skip, true);
  });

  test('it carries the identifiers Path A needs, whatever it decides', () => {
    for (const value of [null, '93 - A']) {
      const out = gateWith(value, daysAgo(1));
      assert.ok(out.org_id && String(out.org_id).length > 0);
      assert.ok(out.request_id);
      for (const key of ['org_name', 'org_website', 'org_linkedin']) {
        assert.ok(Object.prototype.hasOwnProperty.call(out, key), key);
      }
    }
  });

  test('the website is read from the standard field first, then the custom one', () => {
    // The ruling names "the organization's Website URL". In this account that
    // label is a CUSTOM field, while Pipedrive's own `website` is labelled
    // plain "Website", and reps have filled both. Reading only one of them
    // would tell 898 organizations they have no website while a human was
    // looking at one on the record.
    const read = (website, custom) => {
      const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
      const { org } = orgFixture('org_full.json', cfg);
      org.website = website;
      org.custom_fields = { ...(org.custom_fields || {}), [cfg.f_website_url]: custom };
      return gate(normalized, org)[0].json;
    };

    let out = read('https://akuvo.com', null);
    assert.equal(out.org_website, 'https://akuvo.com');
    assert.equal(out.org_website_source, 'website');

    out = read(null, 'https://www.intellistack.com/');
    assert.equal(out.org_website, 'https://www.intellistack.com/');
    assert.equal(out.org_website_source, 'website_url');

    // Both filled and disagreeing: the standard field wins, because it is the
    // one the ruling names by key and the tie has to break somewhere.
    out = read('https://akuvo.com', 'https://www.intellistack.com/');
    assert.equal(out.org_website, 'https://akuvo.com');
    assert.equal(out.org_website_source, 'website');

    for (const [a, b] of [[null, null], ['', ''], ['   ', '  ']]) {
      out = read(a, b);
      assert.equal(out.org_website, null);
      assert.equal(out.org_website_source, null);
    }
  });

  test('the fallback reaches the Clay request, so a custom-field org is scored', () => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture('org_full.json', cfg);
    org.website = null;
    org.custom_fields = { ...(org.custom_fields || {}), [cfg.f_website_url]: 'https://www.intellistack.com/' };
    const [gateOut] = gate(normalized, org);
    const out = clayRequest(gateOut.json)[0].json;
    assert.equal(out.has_website, true);
    assert.equal(out.body.domain, 'intellistack.com');
  });

  test('it reads only the two fields that still exist', () => {
    const source = readNode('IdempotencyGate');
    for (const key of ['f_icp_calculated', 'f_icp_score', 'f_icp_scored_at', 'f_icp_model_version', 'f_icp_final']) {
      assert.ok(!source.includes(key), `IdempotencyGate still reads ${key}`);
    }
    assert.ok(source.includes('f_auto_icp_score'));
    assert.ok(source.includes('f_auto_icp_scored_at'));
  });

  test('what rule 3 costs is written down where it is paid', () => {
    const source = readNode('IdempotencyGate');
    assert.match(source, /model_effective_date/);
    assert.match(source, /an org scored the same day a rubric\s*\n\/\/ ships is not re-scored by rule 3 alone/);
  });
});

// ==========================================================================
describe('BuildClayRequest — one identifier, and it is the website', () => {
  const requestFor = (fixtureName, mutate) => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture(fixtureName, cfg);
    if (mutate) mutate(org);
    const [gateOut] = gate(normalized, org);
    return clayRequest(gateOut.json)[0].json;
  };

  test('an org WITH a website sends a domain and nothing else identifying', () => {
    const out = requestFor('org_full.json');
    assert.equal(out.has_website, true);
    assert.equal(out.domain, 'akuvo.com');
    assert.equal(out.body.domain, 'akuvo.com');
  });

  test('the body is EXACTLY seven keys — the table has a column for each', () => {
    // Not six, not eight. A key the table has no column for vanishes silently,
    // and a column with no key arrives empty on every row; either way nobody
    // finds out until a grade is wrong.
    const KEYS = [
      'org_id', 'deal_id', 'domain', 'request_id',
      'callback_url', 'requested_at', 'model_version',
    ];
    const out = requestFor('org_full.json');
    assert.deepEqual(Object.keys(out.body).sort(), [...KEYS].sort());
  });

  test('the six fields the old contract sent are gone from the body', () => {
    // identifier_kind and identifier_value made a name lookup expressible;
    // company_name, hq_country and hq_state were what a name lookup needed to
    // disambiguate. With no name lookup there is nothing to disambiguate, and
    // linkedin_url was a second identifier for the same company.
    const out = requestFor('org_full.json');
    for (const key of [
      'identifier_kind', 'identifier_value', 'linkedin_url',
      'company_name', 'hq_state', 'hq_country',
    ]) {
      assert.ok(!(key in out.body), `${key} must not be in the Clay payload`);
    }
  });

  test('ids go over the wire as numbers, everything else as it stands', () => {
    const out = requestFor('org_full.json');
    assert.equal(typeof out.body.org_id, 'number');
    assert.equal(typeof out.body.deal_id, 'number');
    assert.equal(out.body.requested_at, cfg.now_iso);
    assert.equal(out.body.model_version, cfg.model_version);
  });

  test('the callback URL comes from CONFIG, not from a literal', () => {
    const out = requestFor('org_full.json');
    assert.equal(out.body.callback_url, cfg.clay_callback_url);
    assert.equal(out.clay_url, cfg.clay_engine_url);
  });

  test('the domain is normalised: lowercase, no scheme, no www., no path', () => {
    for (const [raw, expected] of [
      ['https://www.Akuvo.com/careers', 'akuvo.com'],
      ['WWW.AKUVO.COM', 'akuvo.com'],
      ['http://akuvo.com/', 'akuvo.com'],
      ['akuvo.com', 'akuvo.com'],
    ]) {
      const out = requestFor('org_full.json', (org) => { org.website = raw; });
      assert.equal(out.body.domain, expected, raw);
    }
  });

  // ---- the no-website decision -------------------------------------------
  //
  // A missing website is NOT an error and NOT a fallback. It is an ordinary
  // outcome that produces an ordinary result, and the node says so by
  // returning a decision instead of throwing.

  test('an org with NO website is not sent to Clay at all', () => {
    const out = requestFor('org_no_identifiers.json');
    assert.equal(out.has_website, false);
    assert.ok(!('body' in out), 'there must be no payload to post');
    assert.ok(!('clay_url' in out), 'and nothing to post it to');
    assert.equal(out.website_raw, null);
    assert.match(out.reason, /no Website URL/);
  });

  test('an org with a LinkedIn URL but no website is not sent either', () => {
    // v6.0 fell back to the LinkedIn slug here. A LinkedIn company page is a
    // second identifier for the same company and the table cannot enrich from
    // one, so the fallback bought nothing and hid a missing field.
    const out = requestFor('org_no_website.json');
    assert.equal(out.has_website, false);
    assert.ok(!('body' in out));
  });

  test('a malformed website is treated as missing, and quotes what was there', () => {
    for (const raw of ['akuvo', 'not a domain', '   ', 'n/a', '555-0134', 'co.uk']) {
      const out = requestFor('org_full.json', (org) => { org.website = raw; });
      assert.equal(out.has_website, false, raw);
      assert.ok(!('body' in out), raw);
      if (raw.trim() !== '') {
        assert.equal(out.website_raw, raw, raw);
        assert.match(out.reason, /is not a usable domain/, raw);
      }
    }
  });

  test('a directory in the website field is not a company domain', () => {
    // These normalise perfectly — that is the trap. "linkedin.com" would send
    // the table off to enrich LinkedIn Corporation and come back with a
    // confident grade for a company nobody looked at.
    for (const raw of [
      'https://www.linkedin.com/company/concertai',
      'https://www.crunchbase.com/organization/akuvo',
      'https://akuvo.wixsite.com/home',
      'https://www.facebook.com/akuvo',
    ]) {
      const out = requestFor('org_full.json', (org) => {
        org.website = raw;
        org.linkedin = null;
      });
      assert.equal(out.has_website, false, raw);
      assert.match(out.reason, /directory rather than the company/, raw);
    }
  });

  test('either way it carries the three ids the rest of Path A needs', () => {
    for (const fixtureName of ['org_full.json', 'org_no_identifiers.json']) {
      const out = requestFor(fixtureName);
      assert.ok(out.request_id, fixtureName);
      assert.ok(out.org_id, fixtureName);
      assert.ok(Object.prototype.hasOwnProperty.call(out, 'deal_id'), fixtureName);
    }
  });

  test('the spliced normalizer agrees with engine/normalize.mjs', () => {
    for (const raw of ['https://www.Akuvo.com/careers', 'qcash.io', 'akuvo', '', 'co.uk']) {
      const expected = normalizeDomain(raw);  // none of these is a directory host
      const out = requestFor('org_full.json', (org) => { org.website = raw; });
      assert.equal(out.has_website, expected !== null, raw);
      if (expected !== null) assert.equal(out.body.domain, expected, raw);
    }
  });

  test('the node never reaches for a name or a LinkedIn slug', () => {
    // The rule is easier to keep as "the source does not contain the call"
    // than as "no test happens to cover the path that would make it".
    const source = readNode('BuildClayRequest');
    // Everything after the spliced normalizer — the normalizer still DEFINES
    // those helpers, and other callers still use them; what matters is that
    // this node's own decision never calls one.
    const body = source.slice(source.indexOf('// The one identifier'));
    assert.ok(!/resolveIdentifier\(/.test(body), 'resolveIdentifier must not be called');
    assert.ok(!/normalizeCompanyName\(/.test(body), 'normalizeCompanyName must not be called');
    assert.ok(!/normalizeLinkedInCompanyUrl\(/.test(body), 'the LinkedIn fallback must not be called');
  });
});

// ==========================================================================
describe('BuildNoWebsiteWrite — the skip leaves the same footprint as a score', () => {
  const skipFor = (fixtureName, mutate, config = cfg) => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture(fixtureName, config);
    if (mutate) mutate(org);
    const [gateOut] = gate(normalized, org);
    const decision = clayRequest(gateOut.json)[0].json;
    return runCodeNode(SRC.BuildNoWebsiteWrite, {
      input: [decision],
      nodes: { CONFIG: config, IdempotencyGate: gateOut.json },
    })[0].json;
  };

  test('it writes the SAME two fields a scored run writes, together', () => {
    const out = skipFor('org_no_identifiers.json');
    assert.deepEqual(Object.keys(out.patch), ['custom_fields']);
    assert.deepEqual(
      Object.keys(out.patch.custom_fields).sort(),
      [...cfg.fields_written].sort()
    );
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_score], 'n/a - no website');
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_scored_at], NOW_ISO.slice(0, 10));
  });

  test('Sales Rep ICP Score is not in the patch', () => {
    const out = skipFor('org_no_identifiers.json');
    assert.ok(!(cfg.f_sales_rep_icp_score in out.patch.custom_fields));
  });

  test('the activity says the one thing a human has to do', () => {
    const out = skipFor('org_no_identifiers.json');
    assert.equal(out.subject, cfg.activity_subject_skipped);
    assert.equal(out.type, cfg.activity_type);
    assert.equal(out.body, cfg.activity_no_website);
    assert.match(out.body, /Website URL/);
    assert.ok(out.chars <= cfg.activity_max_chars);
  });

  test('a website that is present but unusable is quoted back', () => {
    const out = skipFor('org_full.json', (org) => { org.website = 'akuvo'; });
    assert.match(out.body, /^Skipped: organization has no Website URL/);
    assert.match(out.body, /reads "akuvo"/);
    assert.ok(out.chars <= cfg.activity_max_chars);
  });

  test('the second deal the same day writes nothing, and still explains itself', () => {
    const out = skipFor('org_no_identifiers.json', (org) => {
      org.custom_fields = {
        ...(org.custom_fields || {}),
        [cfg.f_auto_icp_score]: 'n/a - no website',
        [cfg.f_auto_icp_scored_at]: NOW_ISO.slice(0, 10),
      };
    });
    assert.equal(out.patch_is_empty, true);
    assert.deepEqual(out.patch, {});
    assert.equal(out.body, cfg.activity_no_website);
  });

  test('it refuses to run for an organization that HAS a domain', () => {
    const normalized = normalize(dedupeA(pipedriveFixture('deal_added.v2.json'), {})[0])[0].json;
    const { org } = orgFixture('org_full.json', cfg);
    const [gateOut] = gate(normalized, org);
    const decision = clayRequest(gateOut.json)[0].json;
    assert.throws(() => runCodeNode(SRC.BuildNoWebsiteWrite, {
      input: [decision],
      nodes: { CONFIG: cfg, IdempotencyGate: gateOut.json },
    }), /ICP_WRONG_BRANCH/);
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
describe('BuildOrgPatch — one field, and nothing else', () => {
  const patchFor = (eventName, orgName = 'org_full.json', mutate = null) => {
    const out0 = scored(eventName);
    const { org } = orgFixture(orgName, cfg);
    if (mutate) mutate(org, out0);
    return { out: orgPatch(out0, org)[0].json, parsed: out0, org };
  };

  test('a scored run writes exactly TWO custom fields: the score and its date', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.deepEqual(Object.keys(out.patch), ['custom_fields']);
    assert.deepEqual(Object.keys(out.patch.custom_fields).sort(),
      [cfg.f_auto_icp_score, cfg.f_auto_icp_scored_at].sort());
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_score], '93 - A');
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_scored_at], String(NOW_ISO).slice(0, 10));
  });

  test('the two move together — never one without the other', () => {
    // A score the gate can never age out, or a date that means nothing: both
    // are worse than no write, so the node refuses a partial one by name.
    const source = readNode('BuildOrgPatch');
    assert.match(source, /ICP_PARTIAL_WRITE/);
    for (const name of VALID_FIXTURES) {
      const { out } = patchFor(name);
      const keys = Object.keys(out.patch.custom_fields || {});
      assert.ok(keys.length === 0 || keys.length === 2, `${name} wrote ${keys.length} field(s)`);
    }
  });

  test('the format is "<final> - <grade>"', () => {
    assert.equal(patchFor('icp_scored_A.json').out.auto_icp_score, '93 - A');
    assert.equal(patchFor('icp_scored_B_stable.json').out.auto_icp_score, '74 - B');
    assert.equal(patchFor('icp_scored_contracting_valid.json').out.auto_icp_score, '0 - C');
    assert.equal(patchFor('icp_scored_tier2.json').out.auto_icp_score, '30 - C');
  });

  test('insufficient data writes the words, not a number', () => {
    // "0 - C" would be a lie with the same shape as a real answer.
    const { out } = patchFor('icp_scored_insufficient.json');
    assert.equal(out.auto_icp_score, 'n/a - insufficient data');
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_score], 'n/a - insufficient data');
  });

  test('Sales Rep ICP Score is never in the patch, and the node asserts it', () => {
    for (const name of VALID_FIXTURES) {
      const { out } = patchFor(name);
      const keys = Object.keys(out.patch.custom_fields || {});
      assert.ok(!keys.includes(cfg.f_sales_rep_icp_score), `${name} wrote the human's field`);
    }
    const source = readNode('BuildOrgPatch');
    assert.ok(source.includes('ICP_FORBIDDEN_WRITE'), 'asserted, not merely omitted');
  });

  test('only the two keys CONFIG names can ever appear', () => {
    // An allow-list, not a deny-list: the five v5 fields are deleted from the
    // account, and a deny-list would have to be maintained forever against
    // fields that no longer exist.
    for (const name of VALID_FIXTURES) {
      const { out } = patchFor(name);
      for (const key of Object.keys(out.patch.custom_fields || {})) {
        assert.ok(cfg.fields_written.includes(key), `${name} wrote unlisted key ${key}`);
      }
    }
    assert.deepEqual(cfg.fields_written, [cfg.f_auto_icp_score, cfg.f_auto_icp_scored_at]);
  });

  test('the patch carries NOTHING at the top level — no website, no label, no owner', () => {
    // v6 makes an org mutation other than the one field impossible by shape.
    for (const name of VALID_FIXTURES) {
      const { out } = patchFor(name);
      assert.deepEqual(Object.keys(out.patch), out.patch_is_empty ? [] : ['custom_fields'], name);
    }
  });

  test('website and linkedin are no longer written, even when the org has neither', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_no_identifiers.json');
    assert.deepEqual(Object.keys(out.patch), ['custom_fields']);
    assert.equal(out.patch.website, undefined);
    assert.equal(out.patch.linkedin, undefined);
  });

  test('no churn — the same score AND the same date produce {}', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_auto_icp_score] = '93 - A';
      org.custom_fields[cfg.f_auto_icp_scored_at] = String(NOW_ISO).slice(0, 10);
    });
    assert.deepEqual(out.patch, {});
    assert.equal(out.patch_is_empty, true);
    assert.deepEqual(out.changed_fields, []);
  });

  test('the same grade on a LATER day still writes — the date is what changed', () => {
    // And it has to: the date is what the next gate ages out. A re-score that
    // refreshed the grade and not the clock would make the window meaningless.
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_auto_icp_score] = '93 - A';
      org.custom_fields[cfg.f_auto_icp_scored_at] = '2026-01-01';
    });
    assert.equal(out.patch_is_empty, false);
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_scored_at], String(NOW_ISO).slice(0, 10));
    assert.equal(out.previous_auto_icp_scored_at, '2026-01-01');
  });

  test('a different value produces the write, and reports what it replaced', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields[cfg.f_auto_icp_score] = '61 - B';
    });
    assert.equal(out.patch.custom_fields[cfg.f_auto_icp_score], '93 - A');
    assert.equal(out.previous_auto_icp_score, '61 - B');
  });

  test('a pre-existing Sales Rep ICP Score is left exactly as it was', () => {
    const { out, org } = patchFor('icp_scored_A.json', 'org_full.json', (o) => {
      o.custom_fields[cfg.f_sales_rep_icp_score] = '80 - A (Toby)';
    });
    assert.equal(org.custom_fields[cfg.f_sales_rep_icp_score], '80 - A (Toby)');
    assert.ok(!Object.keys(out.patch.custom_fields).includes(cfg.f_sales_rep_icp_score));
  });
});

// ==========================================================================
describe('BuildActivity — one activity, in plain words', () => {
  const activityFor = (name) => buildActivity(scored(name))[0].json;

  test('it is one done task carrying the body', () => {
    const a = activityFor('icp_scored_A.json');
    assert.equal(a.type, 'task');
    assert.equal(a.subject, 'ICP scored');
    assert.equal(a.done, true);
    assert.ok(a.body.length > 0);
  });

  test('every body fits the 900-character budget', () => {
    for (const name of VALID_FIXTURES) {
      const a = activityFor(name);
      assert.ok(a.body_length <= 900, `${name}: ${a.body_length} chars`);
    }
  });

  test('exactly one CHECK line, always', () => {
    for (const name of VALID_FIXTURES) {
      const a = activityFor(name);
      const checks = a.body.split('\n').filter((l) => l.startsWith('CHECK:'));
      assert.equal(checks.length, 1, `${name} has ${checks.length} CHECK lines`);
    }
  });

  test('no raw field names anywhere in the body', () => {
    // The rule that shapes the whole node: the body is written from structured
    // facts in plain words, never by passing evidence through.
    const RAW = [
      /\bli_[a-z_]+/, /\bapollo[._]/, /\beng_open/, /\beng_headcount/,
      /\bheadcount_\d/, /\bfunding_events/, /\bmissing_inputs/, /\brevenue_estimate/,
      /\bactivation_evidence/, /\brevenue_band_used/, /\brevenue_source/,
      /\[\d+\]/, /_[a-z]+:/,
    ];
    for (const name of VALID_FIXTURES) {
      const a = activityFor(name);
      for (const pattern of RAW) {
        assert.doesNotMatch(a.body, pattern, `${name}: ${pattern} in\n${a.body}`);
      }
    }
  });

  test('a discarded input is written as a sentence', () => {
    const a = activityFor('icp_scored_A.json');
    assert.match(a.body, /^We set aside Apollo revenue \$1\.1M — \$12k\/employee\.$/m);
    assert.doesNotMatch(a.body, /discarded:/);
  });

  test('the activation block says what activation did to the score', () => {
    assert.match(activityFor('icp_scored_A.json').body, /^Activation: accelerating, so the score stands in full\.$/m);
    assert.match(activityFor('icp_scored_B_stable.json').body, /Activation: stable, which takes the score down from 93 to 74\./);
    const zeroed = activityFor('icp_scored_contracting_valid.json').body;
    assert.match(zeroed, /Activation: contracting, which zeroes the score\./);
    assert.match(zeroed, /Without that it would have been 93\./);
  });

  test('an unbacked contracting call is explained, not hidden', () => {
    const a = activityFor('icp_scored_contracting_unbacked.json');
    assert.match(a.body, /nothing backed it up, so it was not applied/);
    assert.match(a.check_line, /^CHECK: the contracting call was not backed/);
  });

  test('the CHECK line picks the most load-bearing doubt, in order', () => {
    assert.match(activityFor('icp_scored_insufficient.json').check_line, /^CHECK: too little was found/);
    assert.match(activityFor('icp_scored_unknown_vertical.json').check_line, /^CHECK: the vertical is not in our rubric/);
    assert.match(activityFor('icp_scored_contracting_unbacked.json').check_line, /^CHECK: the contracting call/);
    assert.match(activityFor('icp_scored_A.json').check_line, /^CHECK: the revenue band is an estimate from headcount/);
    assert.match(activityFor('icp_scored_tier2.json').check_line, /^CHECK: large enough to be relationship-gated/);
  });

  test('the headline says the grade, or says it was not scored', () => {
    assert.match(activityFor('icp_scored_A.json').body, /^ICP A — 93 out of 100\.$/m);
    assert.match(activityFor('icp_scored_insufficient.json').body, /^Not scored — not enough was found/m);
  });

  test('no postings found reads as a sentence, never as zero', () => {
    const a = activityFor('icp_scored_insufficient.json');
    assert.match(a.body, /No job postings were found, which is not the same as none being open\./);
  });

  test('the same input yields the same body, trimmed the same way', () => {
    const first = activityFor('icp_scored_A.json');
    const second = activityFor('icp_scored_A.json');
    assert.equal(first.body, second.body);
  });

  test('a pathological evidence string is trimmed by dropping sentences, not mid-word', () => {
    const event = clayFixture('icp_scored_A.json');
    for (const component of ['industry_vertical', 'company_type', 'stage_maturity', 'revenue_range']) {
      event.cls_all[component].evidence = [`something discarded: ${'x'.repeat(400)}`];
    }
    const a = buildActivity(scored(event))[0].json;
    assert.ok(a.body_length <= 900);
    assert.equal(a.body.split('\n').filter((l) => l.startsWith('CHECK:')).length, 1,
      'the CHECK line survives any budget');
    assert.match(a.body, /^ICP A — 93 out of 100\.$/m, 'and so does the headline');
  });
});

// ==========================================================================
describe('BuildRunSummary', () => {
  const EXPECTED_COLUMNS = [
    'ts', 'requested_at', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
    'domain', 'model_version',
    'industry_vertical', 'industry_level', 'stage_level', 'type_level',
    'geo_level', 'revenue_level', 'revenue_source', 'buying_level',
    'eng_open', 'eng_open_60d_plus',
    'activation_state', 'contracting_guard_applied', 'multiplier', 'composite', 'final',
    'final_without_activation', 'grade', 'status', 'confidence_overall',
    'tier2_candidate', 'flags', 'missing_inputs', 'evidence_json',
    'patch_written', 'auto_icp_score', 'auto_icp_scored_at', 'activity_id', 'error',
  ];

  test('every emitted value is a scalar a human can read in a trace', () => {
    // No nested objects, no arrays: the summary is one flat line per run, and
    // a nested value in it is a value nobody reads.
    for (const name of VALID_FIXTURES) {
      const [row] = runSummary(scored(name));
      for (const [key, value] of Object.entries(row.json)) {
        assert.ok(
          value === null || ['string', 'number', 'boolean'].includes(typeof value),
          `${name} / ${key} is ${typeof value}`
        );
      }
    }
  });

  test('the summary has its keys, in order', () => {
    const out = scored('icp_scored_A.json');
    const [row] = runSummary(out);
    assert.deepEqual(Object.keys(row.json), EXPECTED_COLUMNS);
    assert.equal(EXPECTED_COLUMNS.length, 37);
  });

  test('a scored run fills the score columns', () => {
    const out0 = scored('icp_scored_A.json');
    const { org } = orgFixture('org_full.json', cfg);
    const patch = orgPatch(out0, org)[0].json;
    const activity = buildActivity(out0)[0].json;
    const [row] = runSummary(out0, {
      BuildOrgPatch: patch, BuildActivity: activity, 'POST activity': { data: { id: 7788 } },
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
    assert.equal(r.activity_id, '7788');
    assert.equal(r.auto_icp_score, '93 - A');
    assert.equal(r.error, '');
    assert.equal(r.execution_id, 'exec-test-0001');
  });

  test('a duplicate is flagged and patch_written is false', () => {
    const staticData = {};
    const event = clayFixture('icp_scored_A.json');
    scored(event, staticData);
    const out0 = scored(event, staticData);
    assert.equal(out0._duplicate, true);
    const [row] = runSummary(out0);
    assert.match(row.json.error, /duplicate/);
    assert.equal(row.json.patch_written, false);
    assert.equal(row.json.activity_id, '', 'a duplicate leaves no activity');
    assert.equal(row.json.auto_icp_score, '', 'and writes no field');
  });

  test('evidence_json covers the four classifiers and only those', () => {
    const out = scored('icp_scored_A.json');
    const [row] = runSummary(out);
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
    const [row] = runSummary(out);
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
    const [row] = runSummary(out);
    assert.match(row.json.error, /^conflict:headcount fell 18%/);
  });

  test('the five v6 columns carry what they say', () => {
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.equal(row.json.requested_at, '2026-09-18T10:42:00Z');
    assert.equal(row.json.revenue_source, 'headcount_band');
    assert.equal(row.json.eng_open, 3);
    assert.equal(row.json.eng_open_60d_plus, 2);
    assert.equal(row.json.contracting_guard_applied, false);
    assert.equal(runSummary(scored('icp_scored_contracting_unbacked.json'))[0].json.contracting_guard_applied, true);
  });

  test('an absent hiring count is -1, not 0', () => {
    // A number column cannot hold "unknown" and 0 would be a lie: the provider
    // returning nothing and a company having nothing open are opposite facts.
    const [row] = runSummary(scored('icp_scored_insufficient.json'));
    assert.equal(row.json.eng_open, -1);
    assert.equal(row.json.eng_open_60d_plus, -1);
    assert.equal(runSummary(scored('icp_scored_contracting_valid.json'))[0].json.eng_open, 0,
      'and a real zero is still a zero');
  });
});

// ==========================================================================
describe('BuildErrorContext — a failed run touches nothing', () => {
  const contextFor = (item) => runCodeNode(SRC.BuildErrorContext, { input: [item], nodes: { CONFIG: cfg } })[0].json;

  test('a malformed event yields context, not a patch', () => {
    const event = clayFixture('icp_scored_malformed.json');
    let thrown;
    try { parseScored(event); } catch (error) { thrown = error; }
    assert.ok(thrown, 'the malformed fixture must throw');

    const out = contextFor({ ...event, error: thrown });
    assert.equal(out.error_name, 'IcpMalformedEvent');
    assert.match(out.error_message, /ICP_MALFORMED_EVENT/);
    assert.equal(out.org_untouched, true);
    assert.ok(out.problem_count >= 6, `expected every problem counted, got ${out.problem_count}`);
    assert.ok(out.problems.length > 0);
  });

  test('it builds no patch at all — there is nothing to write', () => {
    const out = contextFor({ org_id: 2695, error: { name: 'X', message: 'y' } });
    assert.equal(out.patch, undefined);
    assert.equal(out.custom_fields, undefined);
    const source = readNode('BuildErrorContext');
    assert.ok(!source.includes('custom_fields'), 'and the source cannot grow one by accident');
  });

  test('it recovers the ids from wherever they survived', () => {
    assert.equal(contextFor({ org_id: 2695, request_id: 'req-1' }).org_id, 2695);
    assert.equal(contextFor({ body: { org_id: 2695, request_id: 'req-1' } }).request_id, 'req-1');
    assert.equal(contextFor({ error: { org_id: 2695, request_id: 'req-1' } }).org_id, 2695);
  });

  test('it never throws, however empty the item', () => {
    for (const item of [{}, { error: null }, { body: {} }]) {
      const out = contextFor(item);
      assert.equal(out.error_name, 'IcpUnknownError');
      assert.equal(out.org_untouched, true);
    }
  });

  test('it caps the problem list so one bad event cannot fill the audit row', () => {
    const many = Array.from({ length: 50 }, (_, i) => `problem ${i}`);
    const out = contextFor({ error: { name: 'E', message: 'm', problems: many } });
    assert.equal(out.problem_count, 50, 'the count is honest');
    assert.equal(out.problems.length, 20, 'the list is bounded');
  });
});
