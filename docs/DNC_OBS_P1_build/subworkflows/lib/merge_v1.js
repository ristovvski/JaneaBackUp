'use strict';
// DNC ledger merge/upsert decision logic v1. Pure function; deterministic given `now`.
// Embedded verbatim in DNC__UpsertLedger__v1 Code node; tested directly by dnc_contract_tests.js.
// Enforces the "enforced-in-code" contract from datatables/CREATE_DATATABLES.md.

// >>> merge_v1 >>>
var DNC_STRENGTH = { explicit_opt_out: 5, negative_reply: 4, replied: 3, employee_connection: 2, manual: 1 };
var DNC_PERMANENT_TYPES = { explicit_opt_out: true, employee_connection: true };

function dncAddMonths(iso, months) {
  var d = new Date(iso);
  var day = d.getUTCDate();
  d.setUTCMonth(d.getUTCMonth() + months);
  if (d.getUTCDate() < day) { d.setUTCDate(0); } // clamp end-of-month overflow
  return d.toISOString();
}

function dncStrongest(a, b) {
  var sa = DNC_STRENGTH[a] || 0, sb = DNC_STRENGTH[b] || 0;
  return sb > sa ? b : a;
}

function dncMergeSources(existing, incoming) {
  var set = [];
  var push = function (s) {
    if (s == null) return;
    String(s).split(',').forEach(function (p) {
      var t = p.trim();
      if (t !== '' && set.indexOf(t) === -1) set.push(t);
    });
  };
  push(existing); push(incoming);
  return set.join(',');
}

// input:  { norm, incoming, config:{ttlMonths, now}, matchedByLinkedin:[], matchedByEmail:[] }
//   norm     = output of normalizeIdentityV1
//   incoming = { entry_type, source, reply_category?, full_name?, pipedrive_person_id?, correlation_id }
// returns: { action:'conflict'|'insert'|'update'|'noop', ... }
function dncMergeDecisionV1(input) {
  var norm = input.norm, incoming = input.incoming, cfg = input.config;
  var byLi = (input.matchedByLinkedin || []).slice();
  var byEm = (input.matchedByEmail || []).slice();
  var now = cfg.now, ttl = cfg.ttlMonths;

  // 1) CONFLICT: both identifiers present & matchable, resolving to DIFFERENT rows/persons.
  if (norm.linkedin_url_norm && norm.email_lc && byLi.length && byEm.length) {
    var liKeys = {}, conflict = false, liRow = byLi[0], emRow = null;
    byLi.forEach(function (r) { liKeys[r.identity_key] = true; });
    for (var i = 0; i < byEm.length; i++) {
      if (!liKeys[byEm[i].identity_key]) { conflict = true; emRow = byEm[i]; break; }
    }
    if (conflict) {
      return { action: 'conflict', linkedin_row: liRow, email_row: emRow,
               reason: 'linkedin and email resolve to different ledger identities' };
    }
  }

  // 2) Candidate rows = union by row id; self-heal if >1 for the resolved identity.
  var seen = {}, candidates = [];
  byLi.concat(byEm).forEach(function (r) {
    var id = (r.id != null ? r.id : r.identity_key);
    if (!seen[id]) { seen[id] = true; candidates.push(r); }
  });

  var record = {
    identity_key: norm.identity_key,
    linkedin_url_norm: norm.linkedin_url_norm,
    email_lc: norm.email_lc,
    full_name: norm.full_name,
    pipedrive_person_id: norm.pipedrive_person_id,
    entry_type: incoming.entry_type,
    source: incoming.source,
    reply_category: (incoming.reply_category != null ? incoming.reply_category : null),
    status: 'active',
    added_at: now,
    expires_at: null,
    removed_at: null,
    removed_reason: null,
    correlation_id: incoming.correlation_id,
    norm_v: norm.norm_v
  };

  // 3) INSERT (no existing row).
  if (candidates.length === 0) {
    record.expires_at = computeExpiry(record.entry_type, record.added_at, ttl);
    return { action: 'insert', record: record, self_heal_remove: [] };
  }

  // 4) MERGE onto a primary (strongest type, then earliest added_at).
  candidates.sort(function (a, b) {
    var d = (DNC_STRENGTH[b.entry_type] || 0) - (DNC_STRENGTH[a.entry_type] || 0);
    if (d !== 0) return d;
    return String(a.added_at || '').localeCompare(String(b.added_at || ''));
  });
  var primary = candidates[0];
  var extras = candidates.slice(1); // duplicates to soft-remove (amendment 2 self-heal)

  var reactivate = (primary.status !== 'active'); // expired/removed + new event => re-suppress
  var mergedType = dncStrongest(primary.entry_type, incoming.entry_type); // never downgrades
  var merged = {
    id: primary.id,
    identity_key: primary.identity_key,
    // fill-if-empty for identity/enrichment fields (never overwrite a set value)
    linkedin_url_norm: primary.linkedin_url_norm || norm.linkedin_url_norm || null,
    email_lc: primary.email_lc || norm.email_lc || null,
    full_name: primary.full_name || norm.full_name || null,
    pipedrive_person_id: (primary.pipedrive_person_id != null ? primary.pipedrive_person_id : norm.pipedrive_person_id),
    entry_type: mergedType,
    source: dncMergeSources(primary.source, incoming.source),
    reply_category: (incoming.reply_category != null ? incoming.reply_category : (primary.reply_category || null)),
    status: 'active',
    added_at: reactivate ? now : primary.added_at,
    removed_at: null,
    removed_reason: null,
    correlation_id: incoming.correlation_id || primary.correlation_id,
    norm_v: norm.norm_v
  };
  merged.expires_at = computeExpiry(merged.entry_type, merged.added_at, ttl);

  // 5) idempotency: if nothing material changed and no duplicates to heal => noop.
  var changed = reactivate
    || merged.entry_type !== primary.entry_type
    || merged.source !== (primary.source || '')
    || merged.expires_at !== (primary.expires_at || (DNC_PERMANENT_TYPES[primary.entry_type] ? null : primary.expires_at))
    || merged.linkedin_url_norm !== (primary.linkedin_url_norm || null)
    || merged.email_lc !== (primary.email_lc || null)
    || merged.full_name !== (primary.full_name || null)
    || String(merged.pipedrive_person_id) !== String(primary.pipedrive_person_id)
    || merged.norm_v !== (primary.norm_v || null);

  if (!changed && extras.length === 0) {
    return { action: 'noop', record: merged, self_heal_remove: [] };
  }
  return { action: 'update', record: merged,
           self_heal_remove: extras.map(function (r) { return r.id != null ? r.id : r.identity_key; }) };
}

function computeExpiry(entry_type, added_at, ttlMonths) {
  // EXPIRY IS DEAD (Nik, 2026-08-31). Every entry_type is permanent; this function returns null
  // for all of them and is kept only so the three call sites and the record shape stay untouched.
  //
  // Why: Melisa's 2026-08-26 ruling replaced TIME-based expiry with REASON-based retention. The
  // registry keeps replies, meetings, sales-created/Surfe, employee connections and explicit
  // opt-outs, and retires rows whose only reason was contact. A six-month TTL on 'replied' and
  // 'negative_reply' applied to precisely the rows that represent a response - it said the
  // response stops mattering, which is the opposite of "only a RESPONSE creates a relationship
  // worth protecting".
  //
  // The TTL had produced 1,353 active rows carrying an expires_at (45 already past, 1,308 on a
  // rolling timer). All 1,353 were nulled the same day; dnc_expiry_job - the only consumer that
  // would ever have acted on the field - is deactivated and preserved.
  //
  // ttlMonths is now unused. It is left in the signature so the call sites do not change.
  return null;
}

function dncSlugifyName(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

// Split-identity corroboration, added 2026-08-20 (Person-69cbb908 case): a "conflict" from
// dncMergeDecisionV1 is sometimes not two different people at all -- it's ONE person split
// across two half-rows because an identifier became readable later than the row that only ever
// had the OTHER identifier. The concrete shape found live: an `employee_connection` row from a
// bulk LinkedIn-connections import (LinkedIn only, no email, no pipedrive_person_id) collides
// with a row some OTHER caller wrote using email+pipedrive_person_id but no LinkedIn (because,
// in Barry's case, S3's own LinkedIn extraction was broken at write time -- see build_dnc.py's
// S3_PERSON_EXTRACT_JS fix, same date). Auto-merging two DIFFERENT real people would be a data
// integrity incident; auto-merging two half-rows of the SAME real person is a data integrity fix.
// The dividing line Nik drew: only merge when (a) the shape matches exactly (one side is an
// identifier-disjoint employee_connection row with no pid; the other carries a pid) AND (b) the
// names corroborate (the pid row's full_name plausibly matches the LinkedIn-only row's slug/name)
// -- anything else stays a conflict, alerted to a human, exactly as before. This function decides
// (a)+(b) and, when both hold, computes the merged survivor record; it never runs automatically
// inside dncMergeDecisionV1 itself, so the base conflict-detection this project already tested
// and depends on stays byte-identical for every case that isn't this exact shape.
//
// input:  the {action:'conflict', linkedin_row, email_row} result from dncMergeDecisionV1,
//         plus { incoming, config:{ttlMonths, now} } (same shape decide_js already has on hand)
// returns either:
//   { corroborated: false }  -- leave as a conflict, unchanged
//   { corroborated: true, record: <merged survivor, same shape as a normal update record>,
//     tombstone: { id, identity_key } }  -- the employee_connection row to soft-remove
function dncSplitIdentityMergeV1(conflictResult, ctx) {
  var liRow = conflictResult.linkedin_row, emRow = conflictResult.email_row;
  var isEmployeeOnlyLI = function (r) {
    return !!r && r.entry_type === 'employee_connection' && r.pipedrive_person_id == null
      && r.email_lc == null && r.linkedin_url_norm != null;
  };
  var isPidCarrying = function (r) { return !!r && r.pipedrive_person_id != null; };

  var empRow = null, pidRow = null;
  if (isEmployeeOnlyLI(liRow) && isPidCarrying(emRow)) { empRow = liRow; pidRow = emRow; }
  else if (isEmployeeOnlyLI(emRow) && isPidCarrying(liRow)) { empRow = emRow; pidRow = liRow; }
  if (!empRow || !pidRow) return { corroborated: false };

  // corroboration: the pid row's own name must plausibly BE the LinkedIn-only row's identity.
  // For a pure-LinkedIn row, identity_key IS the LinkedIn slug (normalizeIdentityV1's own rule),
  // so comparing slugified full_name against that slug directly, or against the LI row's own
  // full_name when it has one, covers both "name recorded on the import" and "name absent, only
  // the slug is known" without guessing at fuzzy/partial matches.
  var pidSlug = dncSlugifyName(pidRow.full_name);
  var empSlug = dncSlugifyName(empRow.full_name) || String(empRow.identity_key || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  var corroborated = !!pidSlug && !!empSlug && pidSlug === empSlug;
  if (!corroborated) return { corroborated: false };

  var incoming = ctx.incoming, cfg = ctx.config;
  var mergedType = dncStrongest(pidRow.entry_type, empRow.entry_type); // never downgrades
  var record = {
    id: pidRow.id,
    identity_key: pidRow.identity_key,           // UNCHANGED -- see rationale above dt_get calls:
    // lookups match on linkedin_url_norm/email_lc columns, never identity_key, so leaving this
    // stable avoids any risk of the upsert matching the WRONG physical row (the LI-only row
    // happens to already have identity_key === the LinkedIn slug -- switching to it here would
    // upsert into that row instead of the intended survivor).
    linkedin_url_norm: pidRow.linkedin_url_norm || empRow.linkedin_url_norm || null,
    email_lc: pidRow.email_lc || empRow.email_lc || null,
    full_name: pidRow.full_name || empRow.full_name || null,
    pipedrive_person_id: pidRow.pipedrive_person_id,
    entry_type: mergedType,
    source: dncMergeSources(pidRow.source, empRow.source),
    reply_category: (incoming.reply_category != null ? incoming.reply_category : (pidRow.reply_category || null)),
    status: 'active',
    added_at: pidRow.added_at, // keep the survivor's own history; this is a fix, not a new event
    removed_at: null,
    removed_reason: null,
    correlation_id: incoming.correlation_id || pidRow.correlation_id,
    norm_v: pidRow.norm_v || 'v1'
  };
  record.expires_at = computeExpiry(record.entry_type, record.added_at, cfg.ttlMonths);

  return {
    corroborated: true,
    record: record,
    tombstone: { id: empRow.id, identity_key: empRow.identity_key },
    emp_row: empRow, pid_row: pidRow
  };
}
// <<< merge_v1 <<<

module.exports = {
  dncMergeDecisionV1: dncMergeDecisionV1,
  computeExpiry: computeExpiry,
  DNC_STRENGTH: DNC_STRENGTH,
  dncStrongest: dncStrongest,
  dncMergeSources: dncMergeSources,
  dncAddMonths: dncAddMonths,
  dncSlugifyName: dncSlugifyName,
  dncSplitIdentityMergeV1: dncSplitIdentityMergeV1
};
