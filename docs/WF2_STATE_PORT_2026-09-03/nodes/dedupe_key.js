// Lifted out of `Dedupe` so the claims-table lookup can run BEFORE the decision. The key
// arithmetic is unchanged - see B-DEDUPE-TS (2026-08-07): keying on the RAW timestamp string
// compared FORMATTING, not time, and the same reply arriving from the webhook and from WF-2R
// produced two keys and a double forward. Epoch ms, with the raw string as the fallback.
const n = $json;
const __ts = (() => {
  const p = Date.parse(n.timestamp ?? '');
  return Number.isFinite(p) ? String(p) : String(n.timestamp ?? '');
})();
const key = [n.event, n.campaign_id, n.sl_lead_id, __ts].map(v => String(v ?? '')).join('|');
const sentKey = 'S|' + String(n.campaign_id ?? '') + '|' + String(n.sl_lead_id ?? '');
const fwdKey = 'F|' + key;
// The lookup needs a value even when a key is missing, or the dataTable node errors on an empty
// filter and we lose the distinction between "nothing to look up" and "table unavailable".
return [{ json: Object.assign({}, n, {
  __dedupe_key: key, __sent_key: sentKey, __forward_key: fwdKey,
  __lookup_dedupe: 'wf2_seen|' + key,
  __lookup_sent: 'wf2_seen|' + sentKey,
  __lookup_forward: 'wf2_seen|' + fwdKey
}) }];
