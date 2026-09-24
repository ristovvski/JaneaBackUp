'use strict';
// dnc_expiry_job planning logic v1. Pure fn over the set of ACTIVE rows.
// Embedded verbatim in dnc_expiry_job "Plan" Code node; tested by expiry_tests.js.

// >>> expire_v1 >>>
var EXP_STRENGTH = { explicit_opt_out: 5, negative_reply: 4, replied: 3, employee_connection: 2, manual: 1 };
var EXP_UNTOUCHABLE = { explicit_opt_out: true }; // never auto-expired/removed by the job

function isoWeekKey(iso) {
  var d = new Date(iso);
  var t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  var day = t.getUTCDay() || 7;               // Mon=1..Sun=7
  t.setUTCDate(t.getUTCDate() + 4 - day);     // nearest Thursday
  var yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  var wk = Math.ceil((((t - yearStart) / 86400000) + 1) / 7);
  return t.getUTCFullYear() + '-W' + (wk < 10 ? '0' + wk : '' + wk);
}

// input: { rows:[activeRows], now }
// returns { to_expire:[{identity_key,added_at}], to_dedup:[{identity_key,added_at,keep_added_at}],
//           expired_count, dedup_count, skipped_ambiguous, week_key, dow }
function planExpiryV1(input) {
  var rows = (input.rows || []).filter(function (r) { return r && r.status === 'active'; });
  var now = input.now;
  var nowMs = new Date(now).getTime();

  // 1) dedup: group by identity_key; keep strongest then earliest; extras (distinct added_at) removed.
  var groups = {};
  rows.forEach(function (r) { (groups[r.identity_key] = groups[r.identity_key] || []).push(r); });
  var to_dedup = [], dedupTargeted = {}, skipped_ambiguous = 0;
  Object.keys(groups).forEach(function (k) {
    var g = groups[k];
    if (g.length < 2) return;
    g.sort(function (a, b) {
      var d = (EXP_STRENGTH[b.entry_type] || 0) - (EXP_STRENGTH[a.entry_type] || 0);
      if (d !== 0) return d;
      return String(a.added_at || '').localeCompare(String(b.added_at || ''));
    });
    var primary = g[0];
    g.slice(1).forEach(function (r) {
      if (r.added_at === primary.added_at) { skipped_ambiguous++; return; } // can't target safely
      to_dedup.push({ identity_key: r.identity_key, added_at: r.added_at, keep_added_at: primary.added_at });
      dedupTargeted[r.identity_key + '|' + r.added_at] = true;
    });
  });

  // 2) expiry: due (expires_at < now), active, not untouchable, not already a dedup target, and
  //    not held for manual review (STAGE 1 addition — additive; rows without expiry_review_pending
  //    behave exactly as before, since undefined/false is falsy).
  var to_expire = [];
  var skipped_review_pending = 0;
  rows.forEach(function (r) {
    if (EXP_UNTOUCHABLE[r.entry_type]) return;
    if (dedupTargeted[r.identity_key + '|' + r.added_at]) return;
    if (r.expires_at == null || r.expires_at === '') return;   // permanent
    if (new Date(r.expires_at).getTime() < nowMs) {
      if (r.expiry_review_pending) { skipped_review_pending++; return; } // held for a human decision
      to_expire.push({ identity_key: r.identity_key, added_at: r.added_at });
    }
  });

  var dow = (new Date(now).getUTCDay() || 7);
  var digest_dow = (input.digest_dow != null ? Number(input.digest_dow) : 1); // default Monday
  return {
    to_expire: to_expire, to_dedup: to_dedup,
    expired_count: to_expire.length, dedup_count: to_dedup.length,
    skipped_ambiguous: skipped_ambiguous, skipped_review_pending: skipped_review_pending,
    week_key: isoWeekKey(now), dow: dow,
    is_digest_day: (dow === digest_dow)
  };
}
// <<< expire_v1 <<<

module.exports = { planExpiryV1: planExpiryV1, isoWeekKey: isoWeekKey };
