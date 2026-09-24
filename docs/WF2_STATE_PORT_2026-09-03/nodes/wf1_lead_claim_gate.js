// Decides whether another execution already owns the create for this (person, campaign).
// FAILS OPEN: if the table cannot be read we create. A duplicate lead is visible and fixable; a
// person with no lead at all is invisible and never chased.
const k = $('Lead Claim Key').item.json;
const row = $json;
// positive shape check - an echoed input item must never read as "already claimed"
const isRow = !!(row && row.family === 'lead_create' && row.claimed_at && row.claim_key);
const claimed = isRow && !!k.__lead_claim_key && row.claim_key === k.__lead_claim_key;
const reason = !k.__lead_claim_key ? 'no_key_create'
             : claimed ? 'already_claimed_use_existing'
             : 'unclaimed_create';
return [{ json: Object.assign({}, k, {
  __lead_already_claimed: claimed, __lead_claim_reason: reason,
  __lead_claim_backend: 'dataTable'
}) }];
