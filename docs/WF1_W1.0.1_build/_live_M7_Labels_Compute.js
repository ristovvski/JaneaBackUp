const __items = (() => {
// M7: effective-rank label read-modify-write.
const cfg = $('CONFIG').item.json;
const person = $('M7 Person Get').item.json.data || {};
const pcf = person.custom_fields || {};
const currentStage = pcf[cfg.fields.stage] || null;
const currentRank = cfg.stageRank[currentStage] || 0;
const incomingStage = $('M7 Build').item.json.targetStage || 'Replied';
const incomingRank = cfg.stageRank[incomingStage] || 4;
const effectiveRank = Math.max(currentRank, incomingRank);
const targetLabel = effectiveRank >= 4 ? cfg.labels.responded
                  : effectiveRank >= 2 ? cfg.labels.connected
                  : cfg.labels.cold;
const targetSet = [];
if (effectiveRank >= 1) targetSet.push(cfg.labels.cold);
if (effectiveRank >= 4) targetSet.push(cfg.labels.responded);

function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}
const lead = selectLead($('M7 Lead Get').item.json.data);
if (!lead) {
  return { json: { __invalid: true, reason: 'no lead', person_id: person.id || null, lead_id: null } };
}
const existing = Array.isArray(lead.label_ids) ? lead.label_ids.slice() : [];
const label_ids = Array.from(new Set([...existing, ...targetSet]));
const changed = !(existing.length === label_ids.length && existing.every(id => label_ids.includes(id)));
return {
  json: {
    __invalid: false,
    person_id: person.id || null,
    lead_id: lead.id,
    label_ids,
    changed,
    label_ids_before: existing,
    currentStage,
    currentRank,
    incomingStage,
    incomingRank,
    effectiveRank,
    targetLabel
  }
};
})();

// Records alert DELIVERY. Runs on BOTH branches (M7 Critical Slack and M7 Alert Suppressed both
// flow here through M7 IF Patch), so the try/catch is what distinguishes them: on the suppressed
// path `M7 Critical Slack` never ran and the lookup throws. The registry must never be written
// from the gate's DECISION - that is what burns a lead when a post fails.
try {
  const __s = $('M7 Critical Slack').item.json;
  // Nik 2026-08-11: delivery means the TEAM saw it. ok:true alone is not delivery - 99
  // historical alerts were ok:true into the OPS channel, and an alert nobody saw was not
  // an alert. Pinned to the team id on purpose, NOT CONFIG.slack_channel_replies: if that
  // were ever pointed back at ops, a config-derived check would silently re-mute everyone.
  const __TEAM = 'C07LTD8UT70';
  if (__s && __s.ok === true && __s.channel === __TEAM) {
    const __k = $('M7 Alert Gate').item.json.__alert_key;
    if (__k) {
      const __sd = $getWorkflowStaticData('global');
      (__sd.__alerted_v1 = __sd.__alerted_v1 || {})[__k] = new Date().toISOString();
    }
  }
} catch (e) { /* alert not sent on this path */ }

return __items;