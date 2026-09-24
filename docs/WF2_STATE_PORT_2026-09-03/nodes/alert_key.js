// Lifted out of `First Reply Gate` so the lookup can run before the decision. The key rule is
// unchanged - STABLE KEY (Nik, 2026-08-31): person id first, then the lead's canonical email,
// never the lead id. A lead that is archived, converted to a deal or pushed past a read horizon
// must not silently reset its own suppression.
const n = (() => { try { return $('Normalize').item.json; } catch (e) { return {}; } })();
const key = String($json.__person_id ?? (n.lead && n.lead.email
              ? String(n.lead.email).trim().toLowerCase() : null) ?? '');
// legacy entries were keyed on the lead id - honoured on READ, never written back.
const legacyKey = $json.__lead_id ? String($json.__lead_id) : null;
return [{ json: Object.assign({}, $json, {
  __alert_key: key || null,
  __legacy_alert_key: legacyKey,
  __lookup_alert: key ? ('wf2_alert|' + key) : '__wf2_no_key__',
  __lookup_alert_legacy: legacyKey ? ('wf2_alert|' + legacyKey) : '__wf2_no_key__'
}) }];
