#!/usr/bin/env node
// ops/heyreach_webhook_scope.mjs — keep the HeyReach webhooks scoped to campaigns.
//
// WHY THIS EXISTS
//
// A HeyReach webhook subscription has a `campaignIds` list. Empty means "every
// campaign AND everything else" — including replies in a connected account's
// private LinkedIn inbox, which have no campaign at all. All six of our
// subscriptions were created with it empty, and the EVERY_MESSAGE_REPLY_RECEIVED
// one delivered 390 private replies into Pipedrive between 12 July and
// 22 September 2026, on 201 people who were in no campaign.
//
// On 22 September all six were scoped to the campaigns that existed that day.
//
// THE RISK THAT CREATES, AND WHY THIS SCRIPT IS THE ANSWER
//
// A campaign created AFTER that day is not in the list, so HeyReach will not
// deliver its events at all — silently. That failure is invisible: no error,
// no alert, just a campaign whose replies never reach the CRM.
//
// So: run this after creating a campaign in HeyReach. It compares the live
// campaign list against every subscription and reports the drift.
//
//   node ops/heyreach_webhook_scope.mjs            report only (default)
//   node ops/heyreach_webhook_scope.mjs --apply    add the missing campaigns
//
// Requires HEYREACH_API_KEY in the environment. Never writes anything without
// --apply, and even then only ever ADDS campaign ids — it does not remove them,
// so a hand-made narrowing on one subscription survives a re-sync.

const KEY = process.env.HEYREACH_API_KEY;
if (!KEY) { console.error('HEYREACH_API_KEY is not set'); process.exit(1); }

const APPLY = process.argv.includes('--apply');
const API = 'https://api.heyreach.io/api/public';
const H = { 'X-API-KEY': KEY, 'Content-Type': 'application/json' };

const post = async (path, body) => {
  const r = await fetch(`${API}${path}`, { method: 'POST', headers: H, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
};

// The API caps limit at 100, so page rather than asking for everything at once
// — a workspace that grows past 100 campaigns must not silently scope to the
// first 100 and drop the rest.
const campaigns = [];
for (let offset = 0; offset < 5000; offset += 100) {
  const page = (await post('/campaign/GetAll', { offset, limit: 100 })).items || [];
  campaigns.push(...page);
  if (page.length < 100) break;
}
const liveIds = campaigns.map((c) => c.id).sort((a, b) => a - b);
const nameById = new Map(campaigns.map((c) => [c.id, c.name]));

const hooks = (await post('/webhooks/GetAllWebhooks', { offset: 0, limit: 100 })).items || [];

console.log(`campaigns in HeyReach: ${liveIds.length}`);
console.log(`webhook subscriptions:  ${hooks.length}`);
console.log(APPLY ? '\nmode: APPLY\n' : '\nmode: report only (pass --apply to fix)\n');

let drift = 0;
for (const hook of hooks) {
  const scoped = hook.campaignIds || [];
  // The dangerous state. An empty list is not "none", it is "everything",
  // which is how private conversations got in.
  const wideOpen = scoped.length === 0;
  const missing = liveIds.filter((id) => !scoped.includes(id));

  const label = `${String(hook.id)} ${String(hook.eventType).padEnd(30)}`;
  if (wideOpen) {
    console.log(`  ${label} UNSCOPED — receives everything, including private inboxes`);
  } else if (missing.length === 0) {
    console.log(`  ${label} ok (${scoped.length} campaigns)`);
    continue;
  } else {
    console.log(`  ${label} missing ${missing.length}: ${missing.map((id) => `${id} ${nameById.get(id) || ''}`.trim()).join(', ')}`);
  }
  drift += 1;

  if (APPLY) {
    const merged = [...new Set([...scoped, ...liveIds])];
    const r = await fetch(`${API}/webhooks/UpdateWebhook?webhookId=${hook.id}`, {
      method: 'PATCH', headers: H, body: JSON.stringify({ campaignIds: merged }),
    });
    if (!r.ok) { console.log(`     FAILED: ${r.status} ${(await r.text()).slice(0, 160)}`); continue; }
    const after = await r.json();
    console.log(`     -> scoped to ${(after.campaignIds || []).length} campaigns`);
  }
}

if (drift === 0) {
  console.log('\nevery subscription is scoped to every campaign — nothing to do.');
} else if (!APPLY) {
  console.log(`\n${drift} subscription(s) need attention. Re-run with --apply.`);
  process.exitCode = 1;
}

// The second line of defence, stated so nobody assumes this script is the only
// one: WF-1's Normalize node drops any event that arrives without a campaign.
// That gate does not depend on this list and covers a campaign this script has
// not been run for — but only for events HeyReach still chooses to deliver.
console.log('\nSecond layer: WF-1 `Normalize` drops any event with no campaign, independently of this list.');
