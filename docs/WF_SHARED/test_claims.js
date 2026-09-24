// WF_SHARED/test_claims.js
// Statics for the claims helper. Run: node test_claims.js
//
// Three of these are run against TWO models of the same storage, side by side:
//   TABLE      - a row per claim, upsert is atomic (what we are porting TO)
//   STATICDATA - one object, loaded at execution start, persisted whole at execution end
//                (what we are porting FROM)
// The point is not that the new code works. It is that the OLD mechanism CANNOT pass, so the
// port is buying something specific and we can name it.

var C = require('./claims.js');
var pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (detail ? '  <- ' + detail : '')); }
}
function section(s) { console.log('\n' + s); }

// ---------------------------------------------------------------- storage models

// Atomic: each upsert lands independently, whatever else is in flight.
function TableModel() {
  this.rows = {};
  this.get = function (key, family) {
    var r = this.rows[key];
    return (r && (!family || r.family === family)) ? [{ json: r }] : [];
  };
  this.upsert = function (row) { this.rows[row.claim_key] = row; };
  this.count = function () { return Object.keys(this.rows).length; };
}

// Read-modify-write on one shared object. An execution loads a snapshot at start and writes the
// WHOLE snapshot back at end - so the last writer wins and everyone else's delta is gone.
function StaticDataModel() {
  this.persisted = {};
  this.begin = function () { return JSON.parse(JSON.stringify(this.persisted)); };
  this.commit = function (snapshot) { this.persisted = snapshot; };
  this.count = function () { return Object.keys(this.persisted).length; };
}

// ---------------------------------------------------------------- static 1

section('STATIC 1 - concurrent executions with DISTINCT keys: every claim must persist');
(function () {
  // Four executions overlapping, exactly as measured on 2026-08-28 11:45:42-11:46:16.
  var keys = ['wf2_seen|a', 'wf2_seen|b', 'wf2_seen|c', 'wf2_seen|d'];

  var t = new TableModel();
  keys.forEach(function (k) { t.upsert(C.claimRowV1({ key: k, family: 'wf2_seen', workflow: 'WF-2' })); });
  ok('TABLE keeps all 4 distinct claims', t.count() === 4, 'kept ' + t.count());

  var s = new StaticDataModel();
  var snaps = keys.map(function () { return s.begin(); });         // all four load at ~the same time
  snaps.forEach(function (snap, i) { snap[keys[i]] = Date.now(); });
  // 35131 started FIRST and ran 34.3s, so it commits LAST with the oldest snapshot.
  [1, 2, 3, 0].forEach(function (i) { s.commit(snaps[i]); });
  ok('STATICDATA loses 3 of the 4 - this is the defect being ported out',
     s.count() === 1, 'kept ' + s.count());
})();

// ---------------------------------------------------------------- static 2

section('STATIC 2 - the same key twice: the second read must say ALREADY HANDLED');
(function () {
  var t = new TableModel();
  var key = C.claimKeyV1('wf2_alert', ['person', '85307']);
  ok('key builds and is family-scoped', key === 'wf2_alert|person|85307', key);

  var first = C.claimLookupV1({ items: t.get(key, 'wf2_alert'), key: key, family: 'wf2_alert' });
  ok('first pass is a MISS', first.status === 'miss', first.status);

  t.upsert(C.claimRowV1({ key: key, family: 'wf2_alert', workflow: 'WF-2', evidence: 'ts=1' }));
  var second = C.claimLookupV1({ items: t.get(key, 'wf2_alert'), key: key, family: 'wf2_alert' });
  ok('second pass is a HIT', second.status === 'hit', second.status);
  ok('the hit is not flagged legacy', second.legacy === false);

  // A legacy key must still be honoured on read...
  var legacy = 'wf2_alert|4ead0900-90d6-11f1-b07d-7faf1dbb463a';
  var t2 = new TableModel();
  t2.upsert(C.claimRowV1({ key: legacy, family: 'wf2_alert', workflow: 'WF-2' }));
  var viaLegacy = C.claimLookupV1({ items: t2.get(legacy, 'wf2_alert'),
                                    key: 'wf2_alert|person|85307', legacyKeys: [legacy],
                                    family: 'wf2_alert' });
  ok('a legacy key still reads as a HIT', viaLegacy.status === 'hit', viaLegacy.status);
  ok('and the hit is marked legacy', viaLegacy.legacy === true);

  // ...but a claim for a DIFFERENT family must not collide with it.
  var crossFamily = C.claimLookupV1({ items: t2.get(legacy, 'wf2_seen'),
                                      key: legacy, family: 'wf2_seen' });
  ok('a different family does not see it', crossFamily.status === 'miss', crossFamily.status);
})();

// ---------------------------------------------------------------- static 3

section('STATIC 3 - redeploy: state must survive a new workflow version');
(function () {
  var t = new TableModel();
  var key = C.claimKeyV1('wf2_seen', ['corr-123']);
  t.upsert(C.claimRowV1({ key: key, family: 'wf2_seen', workflow: 'WF-2' }));
  // A redeploy replaces the workflow definition. The table is not part of it.
  var afterRedeploy = C.claimLookupV1({ items: t.get(key, 'wf2_seen'), key: key, family: 'wf2_seen' });
  ok('TABLE survives redeploy', afterRedeploy.status === 'hit', afterRedeploy.status);

  // staticData is stored ON the workflow. This model cannot show that on its own - the real
  // assertion is the DEV__ twin, which is why static 3 also runs live before the port fires.
  console.log('       (the live half of static 3 runs on the DEV__ twin - offline model cannot' +
              ' prove n8n\'s own persistence)');
})();

// ---------------------------------------------------------------- static 4

section('STATIC 4 - the table echoes its input: must FAIL OPEN, never ALREADY HANDLED');
(function () {
  var key = 'wf2_alert|person|85307';

  // Shape A: the documented error object.
  var errShape = C.claimLookupV1({ items: [{ json: { error: 'ECONNRESET' } }], key: key, family: 'wf2_alert' });
  ok('error object -> unavailable', errShape.status === 'unavailable', errShape.status);

  // Shape B: the input item echoed back with NO marker at all. This is the one that bites, because
  // "did anything come back?" would read it as a hit.
  var echo = C.claimLookupV1({ items: [{ json: { alert_key: key, person_id: 85307, ts: 'x' } }],
                               key: key, family: 'wf2_alert' });
  ok('echoed input -> unavailable, NOT hit', echo.status === 'unavailable', echo.status);
  ok('and it says why', /dt_unavailable_fail_open/.test(echo.reason || ''), echo.reason);

  // A negative check would have got this wrong. Prove the naive rule fails where ours passes.
  var naive = [{ json: { alert_key: key } }].filter(function (i) { return !i.json.error; }).length > 0;
  ok('the naive check (no .error => handled) WOULD have swallowed it', naive === true);

  // An empty read is a genuine miss, not an outage.
  var empty = C.claimLookupV1({ items: [], key: key, family: 'wf2_alert' });
  ok('empty read -> miss', empty.status === 'miss', empty.status);

  // A row missing any shape field is not a row.
  var partial = C.claimLookupV1({ items: [{ json: { claim_key: key, family: 'wf2_alert' } }],
                                  key: key, family: 'wf2_alert' });
  ok('row without claimed_at -> unavailable', partial.status === 'unavailable', partial.status);

  // No key could be built: fail open too, never claim.
  var nokey = C.claimLookupV1({ items: [], key: null, family: 'wf2_alert' });
  ok('unbuildable key -> unavailable', nokey.status === 'unavailable', nokey.status);
  ok('claimKeyV1 refuses an all-empty key', C.claimKeyV1('wf2_alert', ['', null]) === null);
  ok('claimRowV1 refuses to write without a key', (function () {
    try { C.claimRowV1({ family: 'x' }); return false; } catch (e) { return true; }
  })());
})();

// ---------------------------------------------------------------- static 5

section('STATIC 5 - a timestamp we cannot parse must be REPORTED, never silently immortal');
(function () {
  var now = Date.parse('2026-09-03T12:00:00.000Z');
  var oneHundredDaysAgo = '2026-05-26T12:00:00.000Z';

  // The bug being repaired, reproduced against the OLD arithmetic.
  var oldPrune = function (v) { return (now / 1000) - Number(v) > 7776000; };
  ok('OLD: an epoch value 100 days old prunes',
     oldPrune(Math.floor(Date.parse(oneHundredDaysAgo) / 1000)) === true);
  ok('OLD: the same instant as an ISO string NEVER prunes - the immortality bug',
     oldPrune(oneHundredDaysAgo) === false);

  // The new arithmetic, type-asserted.
  var isoRow = { claim_key: 'k', family: 'wf2_alert', claimed_at: oneHundredDaysAgo };
  var e1 = C.claimExpiredV1(isoRow, now);
  ok('NEW: an ISO value 100 days old prunes', e1.expired === true && e1.known === true, JSON.stringify(e1));

  var freshRow = { claim_key: 'k', family: 'wf2_alert', claimed_at: '2026-08-11T12:00:00.000Z' };
  ok('NEW: 23 days old does not prune (nobody is wrongly expired today)',
     C.claimExpiredV1(freshRow, now).expired === false);

  // The whole point of asserting rather than coercing.
  [['a number', 1755000000], ['a garbage string', 'not-a-date'], ['empty', ''], ['missing', undefined]]
    .forEach(function (c) {
      var row = { claim_key: 'k', family: 'wf2_alert', claimed_at: c[1] };
      var age = C.claimAgeV1(row, now);
      var exp = C.claimExpiredV1(row, now);
      ok('claimed_at as ' + c[0] + ' -> age UNKNOWN', age.known === false, JSON.stringify(age));
      ok('claimed_at as ' + c[0] + ' -> expired AND reported', exp.expired === true && exp.known === false
         && /CORRUPT TIMESTAMP/.test(exp.reason || ''), JSON.stringify(exp));
    });

  // Dedupe retention is shorter than alert retention, and both are honoured.
  var eightDays = '2026-08-26T12:00:00.000Z';
  ok('a dedupe claim expires at 7 days',
     C.claimExpiredV1({ claim_key: 'k', family: 'wf2_seen', claimed_at: eightDays }, now).expired === true);
  ok('an alert claim of the same age does not',
     C.claimExpiredV1({ claim_key: 'k', family: 'wf2_alert', claimed_at: eightDays }, now).expired === false);

  // A family the prune does not know about is kept, but loudly.
  var unknown = C.claimExpiredV1({ claim_key: 'k', family: 'something_new', claimed_at: eightDays }, now);
  ok('an unknown family is RETAINED', unknown.expired === false, JSON.stringify(unknown));
  ok('and reported', /UNKNOWN FAMILY/.test(unknown.reason || ''), unknown.reason);
})();

// ---------------------------------------------------------------- build-time invariant

section('BUILD INVARIANT - no Key node may emit a field called claim_key');
(function () {
  ok('a clean Key node passes', C.assertNoClaimKeyEchoV1(['alert_key', 'person_id']) === true);
  ok('a Key node emitting claim_key is refused', (function () {
    try { C.assertNoClaimKeyEchoV1(['claim_key']); return false; } catch (e) { return true; }
  })());
})();

console.log('\n' + (fail ? 'FAIL - ' + fail + ' of ' + (pass + fail) : 'PASS - all ' + pass) +
            ' assertions');
process.exit(fail ? 1 : 0);
