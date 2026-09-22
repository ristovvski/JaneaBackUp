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

/** Every fixture that is supposed to validate. The bad ones are not here. */
const VALID_FIXTURES = [
  'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_bare.json',
  'icp_scored_contracting.json', 'icp_scored_insufficient.json',
  'icp_scored_live_intellistack.json', 'icp_scored_tier2.json',
];

const SRC = {
  Dedupe: readNode('Dedupe'),
  Normalize: readNode('Normalize'),
  IdempotencyGate: readNode('IdempotencyGate'),
  BuildClayRequest: readNode('BuildClayRequest'),
  BuildNoWebsiteWrite: readNode('BuildNoWebsiteWrite'),
  ParseScored: readNode('ParseScored'),
  FailLoudly: readNode('FailLoudly'),
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

/**
 * The whole Path B head: dedupe -> parse. There is no third step. The table
 * scores; ParseScored checks that what arrived can be written.
 */
const scored = (eventName, staticData) => {
  const event = typeof eventName === 'string' ? clayFixture(eventName) : eventName;
  const [parsed] = parseScored(event, staticData);
  return parsed.json;
};

const orgPatch = (out, org) => runCodeNode(SRC.BuildOrgPatch, {
  input: [org],
  nodes: { CONFIG: cfg, ParseScored: out },
});

const buildActivity = (out) => runCodeNode(SRC.BuildActivity, {
  nodes: { CONFIG: cfg, ParseScored: out },
});

const runSummary = (out, extra = {}) => runCodeNode(SRC.BuildRunSummary, {
  nodes: { CONFIG: cfg, ParseScored: out, ...extra },
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
describe('ParseScored — the boundary, and now Path B\'s only thinking', () => {
  test('a valid event parses flat, with the grade already made', () => {
    const [out] = parseScored(clayFixture('icp_scored_A.json'));
    const j = out.json;
    assert.equal(j._path, 'B');
    assert.equal(j._duplicate, false);
    assert.equal(j.request_id, 'req-icp-0001');
    assert.equal(j.org_id, 10001, 'ids stay numeric through the boundary');
    assert.equal(j.deal_id, 55001);
    assert.equal(j.final, 93);
    assert.equal(j.grade, 'A');
    assert.equal(j.status, 'scored');
    assert.match(j.note, /^ICP v6 — Calculated: ICP A/);
  });

  test('it computes nothing — there is no rubric left in n8n', () => {
    // The whole point of the reversal. If a score ever appears here again,
    // there are two implementations of one rubric pretending to be one.
    const [out] = parseScored(clayFixture('icp_scored_A.json'));
    assert.equal(out.json.score, undefined, 'no score object');
    assert.equal(out.json.composite, 92.5, 'the table\'s working is carried, not recomputed');
    const source = readNode('ParseScored');
    assert.ok(!/scoreFromComponents|activationStateFor/.test(source),
      'ParseScored must not contain the scorer or the activation guard');
  });

  test('the note is carried byte for byte', () => {
    for (const name of VALID_FIXTURES) {
      const event = clayFixture(name);
      const [out] = parseScored(event);
      assert.equal(out.json.note, event.note, name);
    }
  });

  test('absent working becomes null, never a guess', () => {
    const [out] = parseScored(clayFixture('icp_scored_bare.json'));
    for (const key of ['composite', 'multiplier', 'industry_level', 'activation_used', 'confidence_overall']) {
      assert.equal(out.json[key], null, key);
    }
    assert.deepEqual(out.json.flags, [], 'flags default to empty, not null');
  });

  test('malformed -> a typed error naming every violation', () => {
    const event = clayFixture('icp_scored_malformed.json');
    assert.throws(() => parseScored(event), (error) => {
      assert.equal(error.name, 'IcpMalformedEvent');
      assert.match(error.message, /ICP_MALFORMED_EVENT/);
      assert.ok(error.problems.length >= 5, `expected >= 5 problems, got ${error.problems.length}`);
      assert.ok(error.problems.some((p) => /org_id must be a positive integer/.test(p)));
      assert.ok(error.problems.some((p) => /grade must be one of/.test(p)));
      assert.ok(error.problems.some((p) => /stage_level must be null or one of/.test(p)));
      assert.ok(error.problems.some((p) => /missing "note"/.test(p)));
      assert.ok(error.problems.some((p) => /unknown top-level key "cls_all"/.test(p)));
      return true;
    });
  });

  test('the v6.0 shape is rejected — this is the regression that caused the rewrite', () => {
    // Execution 60629: Path B answered Clay 200, wrote nothing, told nobody.
    assert.throws(() => parseScored(clayFixture('icp_scored_v60_shape.json')), (error) => {
      assert.equal(error.name, 'IcpMalformedEvent');
      assert.ok(error.problems.some((p) => /missing "grade"/.test(p)));
      assert.ok(error.problems.some((p) => /missing "note"/.test(p)));
      assert.ok(error.problems.some((p) => /unknown top-level key "cls_all"/.test(p)));
      return true;
    });
  });

  test('every fixture the schema accepts, ParseScored accepts', () => {
    for (const name of VALID_FIXTURES) {
      const [out] = parseScored(clayFixture(name));
      assert.equal(out.json._path, 'B', name);
    }
  });

  test('"scored" with a null grade never gets past the boundary', () => {
    const event = clayFixture('icp_scored_A.json');
    event.grade = null;
    assert.throws(() => parseScored(event), /status is "scored" but final or grade is null/);
  });

  test('an empty note never gets past the boundary — the note IS the activity', () => {
    const event = clayFixture('icp_scored_A.json');
    event.note = '';
    assert.throws(() => parseScored(event), /note must be a non-empty string/);
  });
});

// ==========================================================================
describe('BuildOrgPatch — two fields, written together, and nothing else', () => {
  const patchFor = (eventName, orgName = 'org_full.json', mutate = null) => {
    const out0 = scored(eventName);
    const { org } = orgFixture(orgName, cfg);
    if (mutate) mutate(org, out0);
    return { out: orgPatch(out0, org)[0].json, parsed: out0, org };
  };

  test('it writes "<final> - <grade>" and today\'s date, together', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.equal(out.auto_icp_score, '93 - A');
    assert.equal(out.auto_icp_scored_at, NOW_ISO.slice(0, 10));
    assert.deepEqual(
      Object.keys(out.patch.custom_fields).sort(),
      [...cfg.fields_written].sort()
    );
  });

  test('the number written is the table\'s, not one n8n derived', () => {
    const event = clayFixture('icp_scored_A.json');
    // A grade the rubric would never produce from these levels. It is written
    // anyway, because the table owns the rubric now — that is the trade.
    event.final = 41;
    event.grade = 'C';
    const { org } = orgFixture('org_full.json', cfg);
    const out = orgPatch(scored(event), org)[0].json;
    assert.equal(out.auto_icp_score, '41 - C');
  });

  test('insufficient_data writes the label, never a grade-shaped lie', () => {
    const { out } = patchFor('icp_scored_insufficient.json');
    assert.equal(out.auto_icp_score, cfg.label_insufficient);
    assert.ok(!/\d+ - [ABC]/.test(out.auto_icp_score));
  });

  test('Sales Rep ICP Score is never in the patch, and the node asserts it', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.ok(!(cfg.f_sales_rep_icp_score in out.patch.custom_fields));
    const source = readNode('BuildOrgPatch');
    assert.ok(source.includes('ICP_FORBIDDEN_WRITE'));
    assert.ok(source.includes('fields_never_write'));
  });

  test('a pre-existing Sales Rep ICP Score is left exactly as it was', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields = { ...(org.custom_fields || {}), [cfg.f_sales_rep_icp_score]: '80 - A' };
    });
    assert.ok(!(cfg.f_sales_rep_icp_score in out.patch.custom_fields));
  });

  test('the patch body carries nothing at the top level', () => {
    const { out } = patchFor('icp_scored_A.json');
    assert.deepEqual(Object.keys(out.patch), ['custom_fields']);
  });

  test('a re-score with the same value on the same day writes nothing', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields = {
        ...(org.custom_fields || {}),
        [cfg.f_auto_icp_score]: '93 - A',
        [cfg.f_auto_icp_scored_at]: NOW_ISO.slice(0, 10),
      };
    });
    assert.equal(out.patch_is_empty, true);
    assert.deepEqual(out.patch, {});
  });

  test('a changed grade writes BOTH fields, never one of them', () => {
    const { out } = patchFor('icp_scored_A.json', 'org_full.json', (org) => {
      org.custom_fields = {
        ...(org.custom_fields || {}),
        [cfg.f_auto_icp_score]: '56 - B',
        [cfg.f_auto_icp_scored_at]: NOW_ISO.slice(0, 10),
      };
    });
    assert.equal(out.patch_is_empty, false);
    assert.equal(Object.keys(out.patch.custom_fields).length, 2);
  });
});

// ==========================================================================
describe('BuildActivity — the table\'s note, verbatim', () => {
  test('the body is the event\'s note, byte for byte, on every fixture', () => {
    // Not "resembles". Equal. v6.0 rendered its own prose here from the
    // classifier output; there is one author of what a rep reads now.
    for (const name of VALID_FIXTURES) {
      const event = clayFixture(name);
      const [out] = buildActivity(scored(name));
      assert.equal(out.json.body, event.note, name);
      assert.equal(out.json.chars, event.note.length, name);
      assert.equal(out.json.verbatim, true, name);
    }
  });

  test('HTML markup reaches Pipedrive untouched', () => {
    // Pipedrive renders an activity note as HTML — measured on this account:
    // it escapes a stray "<" into "&lt;" on the way in, which only makes sense
    // if it renders on the way out, and it is why a "\n" collapses the whole
    // note into one paragraph. So the table sends <b> and <br>, and n8n must
    // not touch, escape, strip or re-wrap any of it.
    const html = readFileSync(
      join(ROOT, 'tests', 'fixtures', 'clay', 'note_html_rendered.txt'), 'utf8'
    ).replace(/\n$/, '');
    const parsed = scored('icp_scored_A.json');
    parsed.note = html;
    const [out] = buildActivity(parsed);
    assert.equal(out.json.body, html, 'byte-identical, tags and all');
    assert.match(out.json.body, /<b>/);
    assert.match(out.json.body, /<br><br>/);
    assert.ok(!out.json.body.includes('&lt;'), 'n8n must not escape what Pipedrive escapes itself');
  });

  test('a long note is NOT trimmed — verbatim means verbatim', () => {
    const event = clayFixture('icp_scored_A.json');
    event.note = `${event.note}\n${'x'.repeat(4000)}`;
    const [out] = buildActivity(scored(event));
    assert.equal(out.json.body, event.note);
    assert.ok(out.json.chars > 4000);
  });

  test('it renders nothing of its own', () => {
    const source = readNode('BuildActivity');
    for (const gone of ['component_scales', 'CHECK:', 'discarded', 'PROVIDERS', 'activity_max_chars']) {
      assert.ok(!source.includes(gone), `BuildActivity still carries the renderer's ${gone}`);
    }
  });

  test('subject and type come from CONFIG, and the activity is addressed', () => {
    const [out] = buildActivity(scored('icp_scored_A.json'));
    assert.equal(out.json.subject, cfg.activity_subject);
    assert.equal(out.json.type, cfg.activity_type);
    assert.equal(out.json.org_id, 10001);
  });

  test('an empty note is refused rather than posted as a blank activity', () => {
    const parsed = scored('icp_scored_A.json');
    parsed.note = '   ';
    assert.throws(() => buildActivity(parsed), /ICP_EMPTY_NOTE/);
  });
});

// ==========================================================================
describe('BuildRunSummary', () => {
  const EXPECTED_COLUMNS = [
    'ts', 'requested_at', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
    'model_version',
    'industry_level', 'stage_level', 'type_level', 'geo_level', 'revenue_level',
    'activation_used', 'multiplier', 'composite', 'final', 'final_without_activation',
    'grade', 'status', 'confidence_overall', 'tier2_candidate', 'flags',
    'note_chars', 'patch_written', 'auto_icp_score', 'auto_icp_scored_at',
    'activity_id', 'error',
  ];

  test('the summary has its keys, in order', () => {
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.deepEqual(Object.keys(row.json), EXPECTED_COLUMNS);
    assert.equal(EXPECTED_COLUMNS.length, 29);
  });

  test('it records the table\'s working without acting on it', () => {
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.equal(row.json.final, 93);
    assert.equal(row.json.grade, 'A');
    assert.equal(row.json.composite, 92.5);
    assert.equal(row.json.multiplier, 1);
    assert.equal(row.json.industry_level, 10);
    assert.equal(row.json.activation_used, 'Accelerating');
  });

  test('it records the note by LENGTH, not by repeating it', () => {
    const event = clayFixture('icp_scored_A.json');
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.equal(row.json.note_chars, event.note.length);
    assert.ok(!Object.values(row.json).includes(event.note), 'the text belongs in the activity');
  });

  test('a run that wrote nothing says so', () => {
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.equal(row.json.patch_written, false);
    assert.equal(row.json.auto_icp_score, '');
    assert.equal(row.json.activity_id, '');
  });

  test('a run that wrote carries the write through', () => {
    const out0 = scored('icp_scored_A.json');
    const { org } = orgFixture('org_full.json', cfg);
    const patch = orgPatch(out0, org)[0].json;
    const [row] = runSummary(out0, {
      BuildOrgPatch: patch,
      BuildActivity: buildActivity(out0)[0].json,
      'POST activity': { data: { id: 9438 } },
    });
    assert.equal(row.json.patch_written, true);
    assert.equal(row.json.auto_icp_score, '93 - A');
    assert.equal(row.json.activity_id, '9438');
  });

  test('a duplicate is recorded as one, and reaches the summary', () => {
    const staticData = {};
    const event = clayFixture('icp_scored_A.json');
    parseScored(event, staticData);
    const [row] = runSummary(scored(event, staticData));
    assert.match(row.json.error, /duplicate/);
  });

  test('ids are strings in the row, numbers on the wire', () => {
    const [row] = runSummary(scored('icp_scored_A.json'));
    assert.equal(row.json.org_id, '10001');
    assert.equal(row.json.deal_id, '55001');
  });

  test('a null deal_id becomes an empty cell, never the string "null"', () => {
    const [row] = runSummary(scored('icp_scored_insufficient.json'));
    assert.equal(row.json.deal_id, '');
  });

  test('a key added to the row without a column fails loudly', () => {
    const source = readNode('BuildRunSummary');
    assert.match(source, /ICP_SUMMARY_DRIFT/);
  });
});

// ==========================================================================
describe('FailLoudly — a rejected event must not end as a success', () => {
  const failFor = (item) => {
    try {
      runCodeNode(SRC.FailLoudly, { input: [item], nodes: { CONFIG: cfg } });
    } catch (error) {
      return error;
    }
    return null;
  };

  test('it always throws — that is the entire job', () => {
    // Execution 60629: ParseScored rejected the event, the error branch ran to
    // completion, and the execution ended SUCCESS — so settings.errorWorkflow
    // never fired and WF-ERR never posted to Slack. n8n only alerts on a red
    // execution, so the branch has to end red.
    for (const item of [{}, { error_name: 'X' }, { org_id: 1 }]) {
      const error = failFor(item);
      assert.ok(error, `FailLoudly must throw on ${JSON.stringify(item)}`);
      assert.equal(error.name, 'IcpRunFailed');
    }
  });

  test('the message carries what a human needs before opening the execution', () => {
    const error = failFor({
      error_name: 'IcpMalformedEvent',
      error_message: 'ICP_MALFORMED_EVENT: 2 problem(s)',
      org_id: 22586,
      request_id: 'req-7be8d908',
      problems: ['missing "note"', 'unknown top-level key "cls_all"'],
    });
    assert.match(error.message, /ICP_RUN_FAILED/);
    assert.match(error.message, /IcpMalformedEvent/);
    assert.match(error.message, /org_id=22586/);
    assert.match(error.message, /req-7be8d908/);
    assert.match(error.message, /missing "note"/);
    assert.match(error.message, /Clay was answered 200 and does not know/);
  });

  test('it says the organization was left alone', () => {
    assert.match(failFor({}).message, /the organization was not written to/);
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

  test('it re-derives the problem list by RE-VALIDATING the received body', () => {
    // The error's own `.problems` and even its message are dropped crossing
    // n8n's error output (execution 60648 arrived as "unknown error", zero
    // problems). The body the webhook received is intact, and the validator is
    // deterministic, so running it again gives back exactly the list the
    // boundary refused the event for.
    const v60 = clayFixture('icp_scored_v60_shape.json');
    const out = runCodeNode(SRC.BuildErrorContext, {
      input: [{ error: { name: 'Error', message: 'unknown error' } }],
      nodes: { CONFIG: cfg, 'Webhook Clay': { body: v60 } },
    })[0].json;
    assert.equal(out.problems_source, 'revalidated');
    assert.ok(out.problem_count >= 9, `expected the full list, got ${out.problem_count}`);
    assert.ok(out.problems.some((p) => /missing "note"/.test(p)));
    assert.ok(out.problems.some((p) => /unknown top-level key "cls_all"/.test(p)));
  });

  test('it recovers the org id from the webhook when the error lost it', () => {
    // This is what made the failure activity land on NO organization at all
    // (activity 46842, execution 60629).
    const out = runCodeNode(SRC.BuildErrorContext, {
      input: [{ error: { name: 'Error', message: 'unknown error' } }],
      nodes: { CONFIG: cfg, 'Webhook Clay': { body: { org_id: 22586, request_id: 'req-x' } } },
    })[0].json;
    assert.equal(out.org_id, 22586);
    assert.equal(out.request_id, 'req-x');
  });

  test('a real error keeps its own problem list rather than re-deriving one', () => {
    const out = runCodeNode(SRC.BuildErrorContext, {
      input: [{ error: { name: 'IcpMalformedEvent', message: 'm', problems: ['a', 'b'] } }],
      nodes: { CONFIG: cfg },
    })[0].json;
    assert.equal(out.problems_source, 'error');
    assert.deepEqual(out.problems, ['a', 'b']);
  });

  test('a failed run RELEASES its dedupe key, so a fix can be re-sent', () => {
    // Dedupe writes the key on receipt, before anything has judged the
    // payload. Without this, a rejected request_id stays claimed for 48 hours
    // and Clay's corrected redelivery is dropped as a duplicate — silently.
    // A run that failed did not happen.
    const staticData = { global: { seen: { 'clay:scored:req-x:-': 1 }, hourly: {} } };
    const out = runCodeNode(SRC.BuildErrorContext, {
      input: [{ _dedupe_key: 'clay:scored:req-x:-', error: { name: 'E', message: 'm' } }],
      nodes: { CONFIG: cfg },
      staticData,
    })[0].json;
    assert.equal(out.dedupe_key_released, 'clay:scored:req-x:-');
    assert.equal(staticData.global.seen['clay:scored:req-x:-'], undefined, 'the key must be gone');
  });

  test('releasing is a no-op when there is no key to release', () => {
    const staticData = { global: { seen: {}, hourly: {} } };
    const out = runCodeNode(SRC.BuildErrorContext, {
      input: [{ error: { name: 'E', message: 'm' } }],
      nodes: { CONFIG: cfg },
      staticData,
    })[0].json;
    assert.equal(out.dedupe_key_released, null);
  });

  test('it caps the problem list so one bad event cannot fill the audit row', () => {
    const many = Array.from({ length: 50 }, (_, i) => `problem ${i}`);
    const out = contextFor({ error: { name: 'E', message: 'm', problems: many } });
    assert.equal(out.problem_count, 50, 'the count is honest');
    assert.equal(out.problems.length, 20, 'the list is bounded');
  });
});
