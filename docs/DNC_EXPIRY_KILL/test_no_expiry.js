// Static for STEP 3, at CLASS level: no entry_type gets a TTL any more.
// Runs the ACTUAL `Decide` jsCode out of the workflow JSON - no reimplementation.
const fs = require('fs');
const wf = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const decide = wf.nodes.find(n => n.name === 'Decide').parameters.jsCode;

let P = 0, F = 0;
const t = (n, c, e) => { c ? (P++, console.log('  PASS  ' + n))
                           : (F++, console.log('  FAIL  ' + n + (e !== undefined ? '  ' + JSON.stringify(e) : ''))); };

function run(input) {
  const items = [{ json: input }];
  const $ = () => ({ first: () => items[0], item: items[0], all: () => items });
  const $input = { all: () => items, first: () => items[0] };
  const out = new Function('$', '$json', '$input', '$getWorkflowStaticData',
    decide + '\n//# sourceURL=Decide.js')($, input, $input, () => ({}));
  return out.map(o => o.json);
}

const base = (entry_type, extra) => Object.assign({
  norm: { identity_key: 'someone@example.com', email_lc: 'someone@example.com',
          linkedin_url_norm: null, full_name: 'Some One', pipedrive_person_id: 4242,
          norm_v: 'v1' },
  incoming: Object.assign({ entry_type, source: 'pipedrive_responded_label',
                            reply_category: 'unclassified', full_name: 'Some One',
                            date_precision: 'derived',
                            correlation_id: 'static:' + entry_type }, extra || {}),
  config: { ttlMonths: 6, now: '2026-08-31T12:00:00.000Z' },
  matchedByLinkedin: [], matchedByEmail: [],
}, {});

console.log('\n[1] the case that mattered: a NEW reply row');
{
  const r = run(base('negative_reply'))[0];
  const rec = r.record || (r.decision && r.decision.record) || r;
  t('a new negative_reply row is written with expires_at null',
    rec.expires_at === null, { expires_at: rec.expires_at, keys: Object.keys(r).slice(0, 8) });
  t('and it is still active, still protected', rec.status === 'active', rec.status);
  t('added_at is still stamped', !!rec.added_at);
}

console.log('\n[2] CLASS level: NO entry_type gets a TTL');
['negative_reply', 'replied', 'explicit_opt_out', 'employee_connection', 'manual']
  .forEach(et => {
    let rec;
    try {
      const r = run(base(et, et === 'negative_reply' || et === 'replied'
        ? {} : { reply_category: null }))[0];
      rec = r.record || (r.decision && r.decision.record) || r;
    } catch (e) { rec = { expires_at: 'THREW: ' + e.message }; }
    t(et + ' -> expires_at null', rec.expires_at === null || /THREW/.test(String(rec.expires_at)) === false
      ? rec.expires_at === null : false, { got: rec.expires_at });
  });

console.log('\n[3] the TTL code path is gone from the source, not just unreachable');
{
  t('no dncAddMonths call survives in computeExpiry',
    !/return dncAddMonths\(added_at, ttlMonths\)/.test(decide));
  t('computeExpiry still exists and is still called (record shape unchanged)',
    /function computeExpiry/.test(decide) && /computeExpiry\(record\.entry_type/.test(decide));
  t('the rationale is recorded next to the code',
    /2026-08-26 ruling|REASON-based retention/.test(decide));
}

console.log('\n==== ' + P + ' passed, ' + F + ' failed');
process.exit(F ? 1 : 0);
