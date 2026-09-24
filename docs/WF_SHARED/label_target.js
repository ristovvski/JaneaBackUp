// ONE implementation of "which labels does this event earn?".
//
// Embedded verbatim into WF-2's `Body Lead Labels Union` (reply path) and `Body U Lead DNC Label`
// (unsubscribe path) by build_label_target.py, and required directly by test_label_target.js.
// There is no second implementation. The two nodes drifted apart once already - the reply path
// received bounce/OOO/opt-out locks on 2026-08-31 and the unsubscribe path twenty nodes away did
// not, so an opt-out was labelled '3. Responded' and handed to a human as a warm lead.
//
// THE RULE (Nik, 2026-09-02). Pipedrive's handover automation now fires only when the lead's
// labels do NOT contain 'DO NOT CONTACT' or 'Disqualified'. So our job is no longer to withhold
// '3. Responded' - it is to write the TRUTH: they did reply, and here is what they said.
//
//   explicit stop request  -> 3. Responded + DO NOT CONTACT
//   negative reply         -> 3. Responded + Disqualified
//   genuine interest       -> 3. Responded
//   out of office          -> no Responded (no human replied)
//   bounce                 -> no Responded, and no Connected either
//
// THE INVARIANT THAT MAKES IT SAFE: the suppressing label must be in the SAME PATCH as
// '3. Responded'. Two sequential PATCHes would let 'Responded' land alone, and the automation
// would fire in the gap before the suppressing label existed. This function returns one complete
// target set for exactly that reason; callers must never split it.

// Categories come from WF-2's CONFIG.category_map (the Smartlead category ids we write back).
var LT_STOP = ['Do Not Contact'];
var LT_NEGATIVE = ['Not Interested', 'Wrong Person', 'No Longer Working There'];
var LT_INTEREST = ['Interested', 'Meeting Request', 'Information Request'];
var LT_BOUNCEY = ['Sender Originated Bounce'];
var LT_OOO = ['Out Of Office'];

// input:
//   event      'REPLY' | 'UNSUB' | 'BOUNCE'
//   category   classifier category, or null when it did not run / failed
//   is_dnc     classifier's own boolean (an explicit stop it recognised outside the category)
//   is_bounce  the event itself is a bounce
//   is_ooo     Smartlead's own reply_category says auto-reply/OOO
//   existing   label ids already on the lead (never removed)
//   labels     { cold, connected, responded, dnc, disqualified }
// returns { target, union, changed, responded, implied, case }
function labelTargetV1(input) {
  input = input || {};
  var L = input.labels || {};
  var ev = String(input.event || 'REPLY').toUpperCase();
  var cat = input.category == null ? null : String(input.category);
  var inList = function (list, c) { return c != null && list.indexOf(c) !== -1; };

  var kase, target, implied = null;

  if (ev === 'BOUNCE' || input.is_bounce === true || inList(LT_BOUNCEY, cat)) {
    // A bounce proves the opposite of engagement: no human ever saw the message, so it earns
    // neither 'responded' NOR 'connected'.
    kase = 'bounce';
    target = [L.cold];
  } else if (input.is_ooo === true || inList(LT_OOO, cat)) {
    // An autoreply proves the mailbox is live, so 'connected' is earned - but nobody replied.
    kase = 'out_of_office';
    target = [L.cold, L.connected];
  } else if (ev === 'UNSUB' || input.is_dnc === true || inList(LT_STOP, cat)) {
    // An unsubscribe IS an explicit stop request, and a deliberate human act: they received the
    // message, opened it and acted on it. Responded is true; DO NOT CONTACT is what they said.
    kase = 'explicit_stop';
    implied = L.dnc;
    target = [L.cold, L.connected, L.responded, L.dnc];
  } else if (inList(LT_NEGATIVE, cat)) {
    // They replied and the lead cannot proceed. Disqualified suppresses handover; Responded
    // records that a human did answer us.
    kase = 'negative_reply';
    implied = L.disqualified;
    target = [L.cold, L.connected, L.responded, L.disqualified];
  } else if (inList(LT_INTEREST, cat)) {
    kase = 'genuine_interest';
    target = [L.cold, L.connected, L.responded];
  } else {
    // Unclassified, low confidence, or a category we have never seen. A human DID reply, and the
    // reply is already being forwarded to the review address, so handing it to a person is the
    // correct outcome - that is what handover is for. No suppressing label is implied because we
    // do not know what they said, and inventing one would be a guess written into the CRM.
    kase = 'unclassified';
    target = [L.cold, L.connected, L.responded];
  }

  target = target.filter(function (x) { return !!x; });
  var existing = Array.isArray(input.existing) ? input.existing.slice() : [];
  var union = existing.slice();
  for (var i = 0; i < target.length; i++) {
    if (union.indexOf(target[i]) === -1) union.push(target[i]);
  }
  return {
    target: target,
    union: union,
    changed: union.length !== existing.length,
    responded: target.indexOf(L.responded) !== -1,
    implied: implied,
    'case': kase
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { labelTargetV1: labelTargetV1,
                     LT_STOP: LT_STOP, LT_NEGATIVE: LT_NEGATIVE, LT_INTEREST: LT_INTEREST,
                     LT_BOUNCEY: LT_BOUNCEY, LT_OOO: LT_OOO };
}
