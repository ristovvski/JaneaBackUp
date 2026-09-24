// Normalize — Path A only. The single translation layer for the Pipedrive
// webhook body: raw v2 envelope in, stable internal shape out.
//
// Envelope shape per pipedrive.readme.io/docs/guide-for-webhooks-v2:
//   { meta: {...}, data: <current state>, previous: <null on create> }
// meta.id is the id of the TRIGGERING EVENT (the dedupe half).
// meta.entity_id is the id of the affected object (the deal).
// Note meta.is_bulk_edit — not is_bulk_update.
//
// Everything downstream reads $('Normalize'), never the raw body. When
// Pipedrive changes its payload, this is the one node that changes.

const cfg = $('CONFIG').item.json;
const item = $input.first().json;
const raw = item.body || {};
const meta = raw.meta || {};
const deal = raw.data || {};

const str = (v) => (v === undefined || v === null || v === '' ? null : String(v));

const dealId = str(meta.entity_id) || str(deal.id);
const orgId = str(deal.org_id);

// The correlation id every artefact carries. Pipedrive's own correlation_id is
// preferred when present so a Pipedrive support ticket and our audit row can be
// tied together; otherwise it is derived from the event id, which is stable
// across retries.
const pipedriveCorrelation = str(meta.correlation_id);
const requestId = pipedriveCorrelation
  ? `req-${pipedriveCorrelation}`
  : `req-deal-${dealId || 'unknown'}-${str(meta.id) || 'unknown'}`;

const isTriggerEvent =
  meta.action === cfg.trigger_action && meta.entity === cfg.trigger_entity;

// An org-less deal cannot be scored: the whole workflow scores the
// Organization. This is a legitimate skip, not an error — a rep can create a
// deal without linking a company.
const scoreable = Boolean(isTriggerEvent && orgId);

let skipReason = null;
if (!isTriggerEvent) {
  skipReason = `not the trigger event (${meta.entity || '?'}.${meta.action || '?'})`;
} else if (!orgId) {
  skipReason = 'deal has no org_id — nothing to score';
}

return [{
  json: {
    _path: 'A',
    _dedupe_key: item._dedupe_key,
    _duplicate: item._duplicate === true,
    _rate_this_hour: item._rate_this_hour,
    _rate_exceeded: item._rate_exceeded === true,

    request_id: requestId,
    event_id: str(meta.id),
    entity: str(meta.entity),
    action: str(meta.action),
    deal_id: dealId,
    org_id: orgId,

    // Kept for the audit trail, not for logic.
    company_id: str(meta.company_id),
    user_id: str(meta.user_id),
    webhook_id: str(meta.webhook_id),
    change_source: str(meta.change_source),
    is_bulk_edit: meta.is_bulk_edit === true,
    event_timestamp: str(meta.timestamp),
    attempt: meta.attempt === undefined ? null : meta.attempt,

    deal_title: str(deal.title),
    is_trigger_event: isTriggerEvent,
    scoreable,
    skip_reason: skipReason,
    model_version: cfg.model_version,
  },
}];
