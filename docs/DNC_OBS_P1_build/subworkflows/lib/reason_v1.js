'use strict';
// DNC reason-classification + collision-priority + reason-driven expiry override, v1.
// STAGE 1 migration addition (2026-08-07) — ADDITIVE. merge_v1.js's entry_type-based logic
// is untouched; this module only adds new columns on top. Embedded verbatim in
// DNC__UpsertLedger__v1's Code nodes; drift-checked by dnc_contract_tests.js same as merge_v1.

// >>> reason_v1 >>>
// sales_personal_outreach added 2026-08-12 (S3 build): ranks below reply_dnc (a genuine
// customer-driven signal still outranks an internal ownership decision) but above
// manual_offboard_eligible (an active internal sales relationship outranks a passive LinkedIn
// connection) -- per PHASE1_SCENARIOS_SPEC_2026-08-11.md's proposed ladder.
// event_contacted added 2026-08-14 (S4 build): weakest signal of the four scenarios -- "we
// touched them once via an event campaign," not that they responded -- ranks just above
// manual_sheet, per the same spec doc proposal.
// meeting_dnc added 2026-08-14 (S2 build, source resolved by the auditor: label "5. Meeting" UNION
// deal stage "Qualified Meeting Set", Memurai/partner-pipeline scope explicitly excluded per Nik's
// final word): a meeting is deeper engagement than a bare reply but still the person engaging WITH
// us, not an explicit opt-out -- entry_type 'replied' per the spec doc's own proposal, ranked above
// reply_dnc (stronger evidence of engagement than a bare reply). Standard reply-tier TTL (6 months,
// cfg.ttl_months), NOT the permanent opt-out tier -- the spec doc is explicit on this point even
// though Nik's own phrasing ("permanent or long-TTL... strongest protect-signal after explicit
// opt-out") reads more aggressively; followed the written spec over the paraphrase since the spec
// itself already reasons through why meeting_dnc must never borrow the permanent tier.
var REASON_PRIORITY = { client: 0, unsubscribe: 1, meeting_dnc: 2, reply_dnc: 3, sales_personal_outreach: 4, manual_offboard_eligible: 5, event_contacted: 6, manual_sheet: 7, offboard: 8 };
var REASON_TO_ENTRY_TYPE = {
  client: 'explicit_opt_out',
  unsubscribe: 'explicit_opt_out',
  meeting_dnc: 'replied',
  reply_dnc: 'negative_reply',
  // Deliberately 'manual', NOT 'employee_connection': that tier's isOffboardRemovable() semantics
  // are specifically about a departing employee's LinkedIn connections, an unrelated concept this
  // would incorrectly borrow (per the spec doc's own reasoning).
  sales_personal_outreach: 'manual',
  manual_offboard_eligible: 'employee_connection',
  event_contacted: 'manual',
  manual_sheet: 'manual',
  offboard: 'manual'
};
var OFFBOARD_REMOVABLE_REASONS = { manual_offboard_eligible: true };

function reasonEntryType(reason) {
  return REASON_TO_ENTRY_TYPE[reason] || null;
}

// lower priority number wins (0 = client = strongest). Unknown reasons never beat a known one.
function reasonStrongest(a, b) {
  if (a == null) return b;
  if (b == null) return a;
  var pa = REASON_PRIORITY[a], pb = REASON_PRIORITY[b];
  if (pa == null) return b;
  if (pb == null) return a;
  return pb < pa ? b : a;
}

function isOffboardRemovable(reason) {
  return !!OFFBOARD_REMOVABLE_REASONS[reason];
}

// Merge two reason-bearing signals for the SAME identity (in-file seed duplicates, or a live
// event landing on an existing registry row). The loser is never discarded -- it's appended to
// also_flagged, de-duplicated by (reason, source_ref), so offboard scans can still see it even
// though this row's own lifecycle follows only the winning reason.
// existing / incoming shape: { reason, source_ref, source, also_flagged? } -- either may be null.
function reasonMergeV1(existing, incoming) {
  if (!incoming || !incoming.reason) {
    if (!existing || !existing.reason) return null;
    return { reason: existing.reason, source_ref: existing.source_ref || null, also_flagged: (existing.also_flagged || []) };
  }
  if (!existing || !existing.reason) {
    return { reason: incoming.reason, source_ref: incoming.source_ref || null, also_flagged: [] };
  }

  var winnerReason = reasonStrongest(existing.reason, incoming.reason);
  var winner = (winnerReason === existing.reason) ? existing : incoming;
  var loser = (winner === existing) ? incoming : existing;

  var flags = (existing.also_flagged || []).slice();
  if (loser.reason !== winner.reason || (loser.source_ref || null) !== (winner.source_ref || null)) {
    var flag = { reason: loser.reason, source_ref: loser.source_ref || null, source: loser.source || null };
    var dupe = flags.some(function (f) { return f.reason === flag.reason && f.source_ref === flag.source_ref; });
    if (!dupe) flags.push(flag);
  }

  return { reason: winner.reason, source_ref: (winner.source_ref || null), also_flagged: flags };
}

// Amendment 3 (asymmetric-cost rule): reply_dnc only gets a TTL if date_precision === 'derived'.
// 'unknown' => expires_at=null regardless of what merge_v1's entry_type-based computeExpiry said.
// This does NOT set expires_at itself when override.override is false -- caller keeps whatever
// merge_v1 already computed.
function reasonExpiryOverride(reason, datePrecision) {
  if (reason === 'reply_dnc' && datePrecision === 'unknown') return { override: true, expires_at: null };
  return { override: false };
}
// <<< reason_v1 <<<

module.exports = {
  REASON_PRIORITY: REASON_PRIORITY,
  REASON_TO_ENTRY_TYPE: REASON_TO_ENTRY_TYPE,
  reasonEntryType: reasonEntryType,
  reasonStrongest: reasonStrongest,
  isOffboardRemovable: isOffboardRemovable,
  reasonMergeV1: reasonMergeV1,
  reasonExpiryOverride: reasonExpiryOverride
};
