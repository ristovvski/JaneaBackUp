// WF_SHARED/claims.js
// ONE implementation of the atomic-claim decision. Embedded into every workflow that needs it by
// build_*.py; never hand-copied. If you are reading a copy of this inside an n8n Code node, edit
// THIS file and re-run the builder instead.
//
// WHY THIS EXISTS
// n8n's $getWorkflowStaticData('global') is ONE object, loaded at execution start and persisted
// whole at execution end. Two overlapping executions therefore do not lose one key each - the one
// that finishes LAST overwrites the other's entire delta, across every key it touched.
// Measured on WF-2, 2026-08-28 11:45:42-11:46:16: four executions overlapped, all four mutated the
// same object, and the three Claim SENT writes made by the executions that finished first were
// overwritten by the execution that started first and ran 34.3s.
//
// The replacement is a row per claim in the claims data table, keyed and family-scoped, written
// with upsert - which is atomic server-side, so concurrency stops being our problem.
//
// FOUR RULES, ALL BOUGHT WITH AN INCIDENT
//
// 1. POSITIVE SHAPE CHECK. On error some dataTable operations return an error object and others
//    echo the ORIGINAL INPUT ITEMS with no marker at all
//    (memory: n8n-datatable-error-shape-nonuniform). So "did anything come back?" reads an outage
//    as ALREADY HANDLED and swallows the event. We check positively for a real row: claim_key AND
//    family AND claimed_at, all non-empty strings.
//    Build-time invariant: no Key node may emit a field called claim_key, or an echo would pass
//    this check. assertNoClaimKeyEchoV1() below is called by the builders.
//
// 2. FAIL OPEN, AND SAY SO. If the table cannot be read we proceed as if unclaimed and mark the
//    item dt_unavailable_fail_open. A duplicate alert is noise; a swallowed reply is a lost deal.
//
// 3. CLAIM AFTER THE EFFECT IS PROVEN, never at decision time. Claiming first means an alert that
//    failed to post is recorded as delivered and never retried.
//
// 4. ASSERT THE TIMESTAMP TYPE, NEVER COERCE IT. The staticData registry this replaces held mixed
//    ISO strings and epoch numbers and pruned with now - Number(v) > maxAge. Number(ISO) is NaN,
//    every comparison with NaN is false, so 4 of its 11 entries could never expire - three of them
//    real people (Person-67ab0e3f, Person-6cc71013, Person-b70358e4) who would have been permanently
//    un-re-alertable from ~2026-11-09. A value we cannot parse is CORRUPT, and the safe reading of
//    corrupt suppression state is "not suppressed": expire it and report it loudly.

var CLAIM_SHAPE_FIELDS_V1 = ['claim_key', 'family', 'claimed_at'];

// Retention per family. Dedupe families only need to outlive the reconcilers' 48h lookback;
// alert families carry the 90 days the staticData registry used to promise.
var CLAIM_RETENTION_V1 = {
  wf1_alert:   7776000,   // 90d
  wf2_alert:   7776000,   // 90d
  wf1_seen:     604800,   // 7d
  wf2_seen:     604800,   // 7d
  wf2_bounce:   604800,   // 7d
  dedupe:       604800,   // 7d
  lead_create:  604800,   // 7d
  probe:         86400    // 1d - test rows
};

function claimKeyV1(family, parts) {
  var clean = (parts || []).map(function (p) {
    return (p === null || p === undefined) ? '' : String(p).trim().toLowerCase();
  });
  if (!family || clean.length === 0 || clean.every(function (p) { return p === ''; })) return null;
  return String(family) + '|' + clean.join('|');
}

function isRealClaimRowV1(row) {
  if (!row || typeof row !== 'object') return false;
  for (var i = 0; i < CLAIM_SHAPE_FIELDS_V1.length; i++) {
    var v = row[CLAIM_SHAPE_FIELDS_V1[i]];
    if (typeof v !== 'string' || v === '') return false;
  }
  return true;
}

// Age of a claim, TYPE-ASSERTED. Returns {known, ageSec, reason}. Never coerces.
function claimAgeV1(row, nowMs) {
  var now = (typeof nowMs === 'number' && isFinite(nowMs)) ? nowMs : Date.now();
  var raw = row ? row.claimed_at : null;
  if (typeof raw !== 'string' || raw === '') {
    return { known: false, ageSec: null,
             reason: 'claimed_at is ' + (typeof raw) + ', expected a non-empty string' };
  }
  var t = Date.parse(raw);
  if (!Number.isFinite(t)) {
    return { known: false, ageSec: null, reason: 'claimed_at is not parsable as a date: ' + raw };
  }
  return { known: true, ageSec: Math.round((now - t) / 1000), reason: null };
}

// Should this row be pruned? An UNKNOWN age is expired-and-reported, never silently retained.
function claimExpiredV1(row, nowMs, retention) {
  var table = retention || CLAIM_RETENTION_V1;
  var fam = (row && typeof row.family === 'string') ? row.family : null;
  var age = claimAgeV1(row, nowMs);
  if (!age.known) {
    return { expired: true, known: false, ageSec: null, family: fam,
             reason: 'CORRUPT TIMESTAMP - expiring and reporting: ' + age.reason };
  }
  if (fam === null || !Object.prototype.hasOwnProperty.call(table, fam)) {
    // An unknown family is state we do not understand. Keep it, but never quietly.
    return { expired: false, known: true, ageSec: age.ageSec, family: fam,
             reason: 'UNKNOWN FAMILY - retained and reported' };
  }
  var max = table[fam];
  return { expired: age.ageSec > max, known: true, ageSec: age.ageSec, family: fam,
           maxAgeSec: max, reason: null };
}

// The lookup decision. items is the raw output of the dataTable get node.
// Returns {status:'hit'|'miss'|'unavailable', row, matchedKey, legacy, reason}.
function claimLookupV1(input) {
  var items = (input && input.items) || [];
  var key = input && input.key;
  var legacyKeys = (input && input.legacyKeys) || [];
  var family = input && input.family;

  if (!key) return { status: 'unavailable', row: null, matchedKey: null, legacy: false,
                     reason: 'no key could be built for this event' };

  var wanted = {};
  wanted[key] = 'current';
  legacyKeys.forEach(function (k) { if (k && !wanted[k]) wanted[k] = 'legacy'; });

  var sawAnything = false, sawRealRow = false, hit = null, hitKind = null;
  for (var i = 0; i < items.length; i++) {
    var row = (items[i] && items[i].json) ? items[i].json : items[i];
    if (!row || typeof row !== 'object') continue;
    sawAnything = true;
    if (!isRealClaimRowV1(row)) continue;      // rule 1: positive shape check
    sawRealRow = true;
    if (family && row.family !== family) continue;
    var kind = wanted[row.claim_key];
    if (kind && !hit) { hit = row; hitKind = kind; }
  }

  // Items came back but none was a real row: the node echoed its input, or errored.
  if (sawAnything && !sawRealRow) {
    return { status: 'unavailable', row: null, matchedKey: null, legacy: false,
             reason: 'dt_unavailable_fail_open: read returned ' + items.length +
                     ' item(s), none with the shape of a claim row' };
  }
  if (hit) return { status: 'hit', row: hit, matchedKey: hit.claim_key,
                    legacy: hitKind === 'legacy', reason: null };
  return { status: 'miss', row: null, matchedKey: null, legacy: false, reason: null };
}

// The row to upsert once the effect is proven. Legacy keys are honoured on read, never written.
function claimRowV1(input) {
  var i = input || {};
  if (!i.key) throw new Error('claimRowV1: refusing to write a claim with no key');
  if (!i.family) throw new Error('claimRowV1: refusing to write a claim with no family');
  var nowIso = i.nowIso || new Date().toISOString();
  var ev = i.evidence;
  return {
    claim_key: String(i.key),
    family: String(i.family),
    workflow: String(i.workflow || ''),
    event_time: String(i.event_time || nowIso),
    claimed_at: nowIso,
    evidence: (typeof ev === 'string') ? ev
            : ((ev === undefined || ev === null) ? '' : JSON.stringify(ev))
  };
}

// Build-time invariant for the builders (rule 1).
function assertNoClaimKeyEchoV1(keyNodeOutputFields) {
  var bad = (keyNodeOutputFields || []).filter(function (f) { return f === 'claim_key'; });
  if (bad.length) {
    throw new Error('a Key node emits a field named claim_key; an echoed input item would then ' +
                    'pass the positive shape check and an outage would read as ALREADY HANDLED');
  }
  return true;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CLAIM_RETENTION_V1: CLAIM_RETENTION_V1,
    claimKeyV1: claimKeyV1, isRealClaimRowV1: isRealClaimRowV1, claimAgeV1: claimAgeV1,
    claimExpiredV1: claimExpiredV1, claimLookupV1: claimLookupV1, claimRowV1: claimRowV1,
    assertNoClaimKeyEchoV1: assertNoClaimKeyEchoV1
  };
}
