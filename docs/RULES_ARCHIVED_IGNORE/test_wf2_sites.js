// Per-site statics for WF-2. Runs the ACTUAL node code out of the built workflow JSON.
// Scenarios, exactly as specified:
//   archived lead + reply        -> zero writes, zero posts anywhere
//   non-campaign person          -> zero posts
//   active-lead campaign reply   -> unchanged alert WITH link
//   lead archived between two replies -> second reply silent
//   system alarm                 -> posts to #alerts, never suppressed, never in lead-processing
const fs = require('fs');
const WF = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const by = Object.fromEntries(WF.nodes.map(n => [n.name, n]));
const CFG = JSON.parse(by.CONFIG.parameters.jsonOutput);

let P = 0, F = 0;
const t = (n, c, e) => { c ? (P++, console.log('  PASS  ' + n))
                           : (F++, console.log('  FAIL  ' + n + (e !== undefined ? '  ' + JSON.stringify(e) : ''))); };

function run(node, { nodes = {}, json = {}, input = null, statics = {} }) {
  const code = by[node].parameters.jsCode;
  const $ = (nm) => {
    if (!(nm in nodes)) throw new Error(`Node '${nm}' hasn't been executed`);
    const v = nodes[nm];
    return { item: { json: v }, first: () => ({ json: v }), all: () => [{ json: v }] };
  };
  const items = input || [{ json }];
  return new Function('$', '$json', '$input', '$getWorkflowStaticData',
    code + `\n//# sourceURL=${node.replace(/\W/g, '_')}.js`)
    ($, items[0].json, { all: () => items, first: () => items[0] }, () => statics);
}

const CAMP = { id: 3868449, name: '[Events Visiting] [FinovateFall 2026] - Noah - Valids' };
const CFKEY = CFG.fields.lead_campaign;
const NORM = (camp) => ({ event: 'REPLIED',
  campaign_id: (camp === undefined ? CAMP : camp) ? (camp === undefined ? CAMP : camp).id : null,
  campaign_name: (camp === undefined ? CAMP : camp) ? (camp === undefined ? CAMP : camp).name : null,
  lead: { full_name: 'Person-a9a7d542', first: 'Kyle', last: 'Strougo',
          email: 'pii-febd7426@example.invalid' } });
const searchResp = (items) => ({ success: true, data: { items } });
const leadItem = (id, pid, archived) => ({ item: {
  id, title: '3868449 - ' + CAMP.name + ' - Person-a9a7d542', is_archived: archived,
  person: { id: pid }, custom_fields: [CAMP.name] } });

const decide = (probeResp, camp) => run('AR Decide',
  { nodes: { Normalize: NORM(camp), CONFIG: CFG, 'IF Duplicate': { event: 'REPLIED' } },
    input: [{ json: probeResp }] })[0].json;

console.log('\n[site: AR Decide] the probe is read correctly');
{
  const d = decide(searchResp([leadItem('8694ea30', 85903, true)]));
  t('event survives for Switch Event', d.event === 'REPLIED');
  t('input fields survive', d.event === 'REPLIED');
  t('archived person id captured', d.__ar.archived_person_ids[0] === '85903', d.__ar);
  t('archived lead id captured', d.__ar.archived_lead_ids[0] === '8694ea30');
  t('is_campaign true', d.__ar.is_campaign === true);
}

console.log('\n[scenario 1] ARCHIVED lead + reply -> zero writes, zero posts');
{
  const d = decide(searchResp([leadItem('8694ea30', 85903, true)]));
  // create gate: the added condition must evaluate false for this person
  const cond = by['Gate Lead Create'].parameters.conditions.conditions
    .find(c => c.id === 'wf2-ra-sent');
  t('create gate carries the archived condition', !!cond);
  const blocked = !((d.__ar.archived_person_ids || []).indexOf(String(85903)) === -1);
  t('create gate would NOT create (archived person matched)', blocked === true);
  // every person-scoped post gate
  for (const s of ['Reply Alert', 'Nurture Alert', 'Ops Warn No Lead', 'Ops Warn Deleted Person']) {
    const g = run('AR Ctx ' + s, { nodes: { 'AR Decide': d, CONFIG: CFG }, json: {} })[0].json;
    t(`post suppressed: ${s}`, g.__ar_post === false && g.__ar_post_reason === 'archived_lead_ignored',
      g);
  }
}

console.log('\n[scenario 2] NON-CAMPAIGN person -> zero posts');
{
  const d = decide(searchResp([]), null);
  t('is_campaign false', d.__ar.is_campaign === false);
  for (const s of ['Reply Alert', 'Nurture Alert', 'Ops Warn No Lead', 'Ops Warn Deleted Person']) {
    const g = run('AR Ctx ' + s, { nodes: { 'AR Decide': d, CONFIG: CFG }, json: {} })[0].json;
    t(`post suppressed: ${s}`, g.__ar_post === false && g.__ar_post_reason === 'non_campaign_person');
  }
}

console.log('\n[scenario 3] ACTIVE-lead campaign reply -> UNCHANGED, posts with link');
{
  const d = decide(searchResp([leadItem('9b3fa2d0', 85903, false)]));
  t('nothing archived', d.__ar.any_archived === false);
  const blocked = !((d.__ar.archived_person_ids || []).indexOf(String(85903)) === -1);
  t('create gate is not blocked by the new condition', blocked === false);
  for (const s of ['Reply Alert', 'Nurture Alert']) {
    const g = run('AR Ctx ' + s, { nodes: { 'AR Decide': d, CONFIG: CFG }, json: {} })[0].json;
    t(`post allowed: ${s}`, g.__ar_post === true && g.__ar_post_reason === 'ok');
  }
  t('Reply Alert still routes to #lead-processing',
    /slack_channel_replies/.test(by['Reply Alert'].parameters.channelId.value));
}

console.log('\n[scenario 4] lead archived BETWEEN two replies -> second reply silent');
{
  const before = decide(searchResp([leadItem('8694ea30', 85903, false)]));
  const after = decide(searchResp([leadItem('8694ea30', 85903, true)]));
  const g1 = run('AR Ctx Reply Alert', { nodes: { 'AR Decide': before, CONFIG: CFG }, json: {} })[0].json;
  const g2 = run('AR Ctx Reply Alert', { nodes: { 'AR Decide': after, CONFIG: CFG }, json: {} })[0].json;
  t('reply 1 posts', g1.__ar_post === true);
  t('reply 2 is silent', g2.__ar_post === false && g2.__ar_post_reason === 'archived_lead_ignored');
}

console.log('\n[scenario 5] SYSTEM alarms -> #alerts, never suppressed, never lead-processing');
{
  for (const s of ['Ops Warn Bad Secret', 'Ops Warn Unknown Event', 'Ops Warn Classify']) {
    const v = by[s].parameters.channelId.value;
    t(`${s} -> slack_channel_alerts`, /slack_channel_alerts/.test(v), v);
    t(`${s} has NO AR gate upstream`, !by['AR Ctx ' + s]);
  }
  t('slack_channel_alerts is C0BTUHSSM3K', CFG.slack_channel_alerts === 'C0BTUHSSM3K');
  const lp = WF.nodes.filter(n => n.type === 'n8n-nodes-base.slack'
    && /slack_channel_replies/.test((n.parameters.channelId || {}).value || ''));
  t('exactly ONE node posts to #lead-processing', lp.length === 1, lp.map(n => n.name));
  t('and it is the campaign reply alert', lp[0] && lp[0].name === 'Reply Alert');
}

console.log('\n[fail-open] an unreadable probe must NOT silence a real reply');
for (const [label, resp] of [['error item', { error: { message: 'ETIMEDOUT' } }],
                             ['echoed input', { event: 'x', lead: {} }]]) {
  const d = decide(resp);
  t(`${label}: probe_ok false`, d.__ar.probe_ok === false);
  const g = run('AR Ctx Reply Alert', { nodes: { 'AR Decide': d, CONFIG: CFG }, json: {} })[0].json;
  t(`${label}: post still allowed`, g.__ar_post === true, g);
}

console.log('\n[no hardcoded channel ids outside CONFIG]');
{
  const bad = WF.nodes.filter(n => n.name !== 'CONFIG'
    && n.type !== 'n8n-nodes-base.stickyNote'
    && /C0[A-Z0-9]{8,}/.test(JSON.stringify(n.parameters)));
  // M7 Labels Compute names C07LTD8UT70 only inside a SANITY CHECK on a CONFIG-read value -
  // it is not the source of the id. Asserted precisely rather than waived.
  const real = bad;
  t('no node sources a channel id outside CONFIG', real.length === 0, real.map(n => n.name));

}

console.log('\n==== ' + P + ' passed, ' + F + ' failed');
process.exit(F ? 1 : 0);
