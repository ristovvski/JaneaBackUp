// WF-1 duplicate-lead guard. `Lead Search` -> `Lead Create Gate` -> `Create Lead` is check-then-act
// with nothing durable between the read and the write: two executions for the same person and
// campaign that overlap both read "no lead exists" and both create one.
//
// WHAT THIS ACTUALLY BUYS, stated honestly. A get-then-upsert does not serialise two writers in
// the same millisecond. What it does is make the guard DURABLE ACROSS EXECUTIONS: today the only
// evidence that a lead is being created lives in a Pipedrive list read, which has a lag and a
// horizon, so a second execution seconds or minutes later can still see nothing. With a claim row
// it sees the claim. That is the gap that produced the one duplicate we found.
//
// Observed instances attributable to the race: ZERO (the single duplicate in 2,132 campaign leads
// carried no channel_id and so did not come from `Create Lead`). This is closed because it is the
// same class as WF-2's stores, not because it is burning.
const pid = $('PID Resolved').item.json.person_id;
const camp = (($('Normalize').item.json.campaign || {}).name) || null;
const key = (pid && camp) ? ('lead_create|' + String(pid) + '|' + String(camp).trim().toLowerCase())
                          : null;
return [{ json: Object.assign({}, $json, {
  __lead_claim_key: key,
  // a value is always needed or the dataTable filter errors on empty and we lose the distinction
  // between "no key" and "table unavailable"
  __lookup_lead_claim: key || '__wf1_no_key__'
}) }];
