'use strict';
// Frozen normalization v1 for the DNC ledger. DO NOT edit rules here without bumping to v2
// (see NORMALIZATION_V1.md). Every writer stamps norm_v; readers must not "improve" silently.
// This exact function body (between the >>> / <<< markers) is embedded verbatim in the
// DNC__*_v1 Code nodes; dnc_contract_tests.js asserts the JSON copies match this file.

// >>> normalize_v1 >>>
function normalizeIdentityV1(input) {
  var NORM_V = 'v1';
  input = input || {};
  var out = {
    norm_v: NORM_V,
    linkedin_url_norm: null,
    linkedin_slug: null,
    email_lc: null,
    identity_key: null,
    linkedin_unmatchable: false,
    full_name: (input.full_name != null ? String(input.full_name).trim() : null) || null,
    pipedrive_person_id: (input.pipedrive_person_id != null && input.pipedrive_person_id !== '')
      ? Number(input.pipedrive_person_id) : null,
    notes: []
  };

  // --- LinkedIn: lowercase; canonical https://www.linkedin.com/in/{slug}; strip
  //     query/fragment/trailing slash; percent-decode slug; non-/in/ URLs => not matchable.
  var li = input.linkedin_url;
  if (li != null && String(li).trim() !== '') {
    var raw = String(li).trim().toLowerCase();
    var afterIn = null;
    var m = raw.match(/\/in\/([^/?#]+)/);
    if (m && m[1]) {
      afterIn = m[1];
    }
    if (afterIn == null) {
      // company / school / sales-nav / bare handle / anything without /in/ => unmatchable
      out.linkedin_unmatchable = true;
      out.notes.push('linkedin_not_/in/_url');
    } else {
      var slug = afterIn.replace(/\/+$/, ''); // trailing slash(es)
      try { slug = decodeURIComponent(slug); } catch (e) { out.notes.push('linkedin_percent_decode_failed'); }
      slug = slug.replace(/\/+$/, '').trim();
      if (slug === '') {
        out.linkedin_unmatchable = true;
        out.notes.push('linkedin_empty_slug');
      } else {
        out.linkedin_slug = slug;
        out.linkedin_url_norm = 'https://www.linkedin.com/in/' + slug;
      }
    }
  }

  // --- Email: trim + lowercase ONLY. No plus-tag or dot stripping in v1 (false-merge risk).
  var em = input.email;
  if (em != null && String(em).trim() !== '') {
    var e = String(em).trim().toLowerCase();
    if (e.indexOf('@') > 0 && e.indexOf('.', e.indexOf('@')) > 0) {
      out.email_lc = e;
    } else {
      out.notes.push('email_shape_invalid');
    }
  }

  // --- identity_key: linkedin slug if matchable, else email_lc.
  if (out.linkedin_slug) {
    out.identity_key = out.linkedin_slug;
  } else if (out.email_lc) {
    out.identity_key = out.email_lc;
  } else {
    out.identity_key = null; // caller must handle: unmatchable input => alert / usage hint
  }
  return out;
}
// <<< normalize_v1 <<<

module.exports = { normalizeIdentityV1: normalizeIdentityV1 };
