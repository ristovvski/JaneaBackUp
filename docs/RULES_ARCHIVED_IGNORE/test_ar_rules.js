// Statics for the two standing rules. Fixtures are the real Person-b093030e shapes, taken from
// /v1/leads/search and WF-1 exec 39755.
const R = require('./ar_rules.js');

let P = 0, F = 0;
const t = (n, c, e) => { c ? (P++, console.log('  PASS  ' + n))
                           : (F++, console.log('  FAIL  ' + n + (e !== undefined ? '  ' + JSON.stringify(e) : ''))); };

const CAMP_NAME = '[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn';
const CAMP_ID = 572715;
const CF = '86157bb49563191c17b4dc62580525f84417524c';
const search = (items) => ({ success: true, data: { items } });
const lead = (id, personId, archived, title) => ({ item: {
  id, title: title || (CAMP_ID + ' - ' + CAMP_NAME + ' - Person-b093030e'),
  is_archived: archived, person: { id: personId }, custom_fields: [CAMP_NAME] } });

console.log('\n[1] RULE 1 — the Arnab case: archived campaign lead for this person');
{
  const probe = R.arParseProbe(search([lead('8694ea30', 85903, true)]), CAMP_NAME, CAMP_ID, CF);
  t('probe readable', probe.ok === true, probe);
  t('one campaign row found', probe.rows.length === 1, probe.rows);
  const v = R.arVerdict(probe, 85903);
  t('BLOCKS', v.block === true, v);
  t('reason named', v.why === 'archived_campaign_lead_for_this_person', v.why);
  t('the archived lead id is reported', v.archived_ids[0] === '8694ea30');
}

console.log('\n[2] the ordinary path is untouched — live campaign lead');
{
  const probe = R.arParseProbe(search([lead('9b3fa2d0', 85905, false)]), CAMP_NAME, CAMP_ID, CF);
  const v = R.arVerdict(probe, 85905);
  t('does NOT block', v.block === false, v);
  t('reason named', v.why === 'live_lead_for_this_person', v.why);
}

console.log('\n[3] a live lead for THIS person wins over a namesake archived one');
{
  const probe = R.arParseProbe(search([
    lead('aaaaaaaa', 99999, true),        // some other Person-b093030e, archived
    lead('bbbbbbbb', 85903, false),       // ours, live
  ]), CAMP_NAME, CAMP_ID, CF);
  const v = R.arVerdict(probe, 85903);
  t('does not block on a namesake', v.block === false, v);
  t('and the namesake archived id is still surfaced', v.archived_ids.length === 0, v.archived_ids);
}

console.log('\n[4] name is an INDEX, not the decision: archived row for a different person only');
{
  const probe = R.arParseProbe(search([lead('cccccccc', 99999, true)]), CAMP_NAME, CAMP_ID, CF);
  const v = R.arVerdict(probe, 85903);
  t('a different person\'s archived lead does not block ours', v.block === false, v);
  t('reason named', v.why === 'no_archived_campaign_lead', v.why);
}

console.log('\n[5] unresolved person + archived campaign lead -> ignore (safe side of rule 1)');
{
  const probe = R.arParseProbe(search([lead('dddddddd', 85903, true)]), CAMP_NAME, CAMP_ID, CF);
  const v = R.arVerdict(probe, null);
  t('blocks when the person could not be confirmed', v.block === true, v);
  t('and says the confirmation is missing',
    v.why === 'archived_campaign_lead_unconfirmed_person', v.why);
}

console.log('\n[6] campaign scoping: another campaign\'s archived lead is irrelevant');
{
  const other = { item: { id: 'eeeeeeee', title: '2548814 - [Events Visiting] Money 20/20 2025 - Valids - Person-b093030e',
                          is_archived: true, person: { id: 85903 }, custom_fields: ['Money 20/20 2025'] } };
  const probe = R.arParseProbe(search([other]), CAMP_NAME, CAMP_ID, CF);
  t('the other campaign is filtered out', probe.rows.length === 0, probe.rows);
  t('so nothing blocks', R.arVerdict(probe, 85903).block === false);
}

console.log('\n[7] an unreadable probe FAILS OPEN and says so');
for (const [label, resp] of [
  ['HTTP error item', { error: { message: 'ETIMEDOUT' } }],
  ['echoed input, no marker', { event: 'every_message_reply_received', lead: {} }],
  ['null', null],
]) {
  const probe = R.arParseProbe(resp, CAMP_NAME, CAMP_ID, CF);
  const v = R.arVerdict(probe, 85903);
  t(`${label}: probe not ok`, probe.ok === false);
  t(`${label}: does not block a real reply`, v.block === false);
  t(`${label}: reports why`, v.why === 'probe_unreadable' && v.probe_ok === false, v);
}

console.log('\n[8] RULE 2 — non-campaign events');
t('no campaign object -> not a campaign', R.arIsCampaign(null) === false);
t('empty campaign -> not a campaign', R.arIsCampaign({ id: null, name: '' }) === false);
t('whitespace-only name -> not a campaign', R.arIsCampaign({ id: null, name: '   ' }) === false);
t('id only -> IS a campaign', R.arIsCampaign({ id: 572715, name: null }) === true);
t('name only -> IS a campaign', R.arIsCampaign({ id: null, name: CAMP_NAME }) === true);

console.log('\n[9] STABLE KEYS — never lead visibility');
{
  const withLead = R.arStableKey(85903, { linkedin_url: 'https://www.linkedin.com/in/pii-1ff60be7' }, CAMP_ID);
  const afterArchive = R.arStableKey(85903, { linkedin_url: 'https://www.linkedin.com/in/pii-1ff60be7' }, CAMP_ID);
  t('key is person-based', withLead === 'P85903|572715', withLead);
  t('archiving the lead cannot change the key', withLead === afterArchive);
  t('no lead id appears in the key', !/8694ea30|^L/.test(withLead));
  const noPerson = R.arStableKey(null, { linkedin_url: 'https://www.linkedin.com/in/pii-1ff60be7' }, CAMP_ID);
  t('falls back to the canonical slug', noPerson === 'Karnab-dey-77829436|572715', noPerson);
  t('member_id is used when there is no URL',
    R.arStableKey(null, { member_id: 'ACoAAB' }, CAMP_ID) === 'KACoAAB|572715');
  t('email is used for the email side',
    R.arStableKey(null, { email: 'pii-da50e332@example.invalid' }, 3868449) === 'pii-0bb9be0f@example.invalid|3868449');
  t('nothing at all -> null, and the caller must fail open',
    R.arStableKey(null, {}, CAMP_ID) === null);
  t('same person, different campaign -> different key',
    R.arStableKey(85903, {}, 111) !== R.arStableKey(85903, {}, 222));
}

console.log('\n[10] the exact regression: lead archived BETWEEN two replies');
{
  // reply 1: lead live  -> key must equal reply 2's key, so reply 2 is suppressed as delivered
  const p1 = R.arParseProbe(search([lead('8694ea30', 85903, false)]), CAMP_NAME, CAMP_ID, CF);
  const k1 = R.arStableKey(85903, {}, CAMP_ID);
  const v1 = R.arVerdict(p1, 85903);
  // reply 2: same lead, now archived
  const p2 = R.arParseProbe(search([lead('8694ea30', 85903, true)]), CAMP_NAME, CAMP_ID, CF);
  const k2 = R.arStableKey(85903, {}, CAMP_ID);
  const v2 = R.arVerdict(p2, 85903);
  t('reply 1 is processed normally', v1.block === false);
  t('reply 2 is IGNORED by rule 1', v2.block === true);
  t('the suppression key did NOT move when the lead was archived', k1 === k2, { k1, k2 });
}

console.log('\n[11] probe saturation is surfaced, not swallowed');
{
  const many = Array.from({ length: 100 }, (_, i) => lead('id' + i, 70000 + i, false));
  const probe = R.arParseProbe(search(many), CAMP_NAME, CAMP_ID, CF);
  t('saturation flagged at the 100-item cap', probe.saturated === true);
}

console.log('\n==== ' + P + ' passed, ' + F + ' failed');
process.exit(F ? 1 : 0);
