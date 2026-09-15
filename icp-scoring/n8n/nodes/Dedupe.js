// Dedupe — deterministic key + TTL'd static-data ledger, both paths.
//
// Reads only IDENTITY fields from the raw body (which event, which entity).
// Every business field is read in Normalize (Path A) or ParseScored (Path B).
//
// The two paths treat a duplicate DIFFERENTLY, on purpose:
//
//   Path A (Pipedrive)  duplicate -> return []  — drop it, nothing downstream.
//                       A redelivered deal.create must not fan out a second
//                       Clay request and burn a second credit.
//
//   Path B (Clay)       duplicate -> pass through with _duplicate: true.
//                       The write gates then skip the PATCH and the note, but
//                       the audit row is still written and flagged. A dedupe
//                       that leaves no trace is indistinguishable from a lost
//                       event when someone asks why an org was not scored.
//
// The key must NOT include meta.attempt: Pipedrive increments it on every
// retry, so a key containing it would treat each retry as a new event — the
// exact opposite of dedupe.

// CONFIG on Path A, CONFIG B on Path B. The two Set nodes hold the same JSON,
// but a Code node may only reference a node that is CONNECTED upstream of it:
// n8n raises a "no connection" expression error otherwise, and in the task
// runner that error's own constructor then throws
// `Cannot assign to read only property 'name'`, which hides the real message
// completely. A node that runs on both paths therefore has to ask for
// whichever CONFIG is upstream of it. Kept byte-identical across the nodes
// that need it; tests/static/workflow_review.test.mjs enforces that.
let cfg = null;
try { cfg = $('CONFIG').item.json; } catch (e) { cfg = null; }
if (cfg === null || cfg === undefined) {
  try { cfg = $('CONFIG B').item.json; } catch (e) { cfg = null; }
}
if (cfg === null || cfg === undefined) {
  throw new Error('ICP_NO_CONFIG: neither CONFIG nor CONFIG B is upstream of this node');
}

// CONFIG is a raw-mode Set node, so it REPLACES the item: by the time we get
// here $input holds the config object, not the payload. The body therefore has
// to come from the webhook node itself. $('Name') throws when that node has not
// run in this execution, which is exactly how we tell the two paths apart.
let raw = null;
try { raw = $('Webhook Pipedrive').item.json.body; } catch (e) { raw = null; }
if (raw === null || raw === undefined) {
  try { raw = $('Webhook Clay').item.json.body; } catch (e) { raw = null; }
}
if (raw === null || raw === undefined) raw = {};

const ttlMs = (cfg.dedupe_ttl_hours || 48) * 3600 * 1000;
const now = Date.now();

// ---------------------------------------------------------------------------
// Which path is this?
// ---------------------------------------------------------------------------
let path = null;
let key = null;

const meta = raw.meta;
if (meta && meta.id !== undefined && meta.id !== null) {
  path = 'A';
  const dealId = meta.entity_id === undefined || meta.entity_id === null ? '' : String(meta.entity_id);
  key = `pipedrive:${meta.entity || 'unknown'}:${dealId}:${String(meta.id)}`;
} else if (raw.event === cfg.clay_event_name) {
  path = 'B';
  const requestId = raw.request_id === undefined || raw.request_id === null ? '' : String(raw.request_id);
  const eventId = raw.event_id === undefined || raw.event_id === null ? '' : String(raw.event_id);
  if (requestId === '' || eventId === '') {
    // Without both halves the ledger key collides across every callback and
    // would drop all of them after the first. Fail loudly instead.
    const error = new Error(
      `ICP_MALFORMED_EVENT: ${cfg.clay_event_name} needs both request_id and event_id ` +
      `to be deduped (got request_id="${requestId}", event_id="${eventId}")`
    );
    error.name = 'IcpMalformedEvent';
    throw error;
  }
  key = `clay:scored:${requestId}:${eventId}`;
} else {
  // Both endpoints are authenticated, so an unrecognised body is not a passing
  // scanner — it is a real payload we do not understand, and staying quiet
  // about it means an org silently never gets scored.
  const error = new Error(
    'ICP_UNKNOWN_PAYLOAD: body matched neither the Pipedrive v2 envelope ' +
    '(meta.id) nor the Clay callback (event === "' + cfg.clay_event_name + '")'
  );
  error.name = 'IcpUnknownPayload';
  throw error;
}

// ---------------------------------------------------------------------------
// Ledger
// ---------------------------------------------------------------------------
const sd = $getWorkflowStaticData('global');
sd.seen = sd.seen || {};
sd.hourly = sd.hourly || {};

for (const k of Object.keys(sd.seen)) {
  if (now - sd.seen[k] > ttlMs) delete sd.seen[k];
}

const duplicate = Boolean(sd.seen[key]);
if (!duplicate) sd.seen[key] = now;

// ---------------------------------------------------------------------------
// Anomaly gate: events per hour, counted here because this node already owns
// the static data. Warned on as a non-blocking tee; never blocks the spine.
// ---------------------------------------------------------------------------
const hourKey = new Date(now).toISOString().slice(0, 13);
for (const k of Object.keys(sd.hourly)) {
  if (k < new Date(now - 6 * 3600 * 1000).toISOString().slice(0, 13)) delete sd.hourly[k];
}
sd.hourly[hourKey] = (sd.hourly[hourKey] || 0) + 1;
const rateThisHour = sd.hourly[hourKey];
const rateExceeded = rateThisHour > (cfg.max_events_per_hour || Infinity);

if (path === 'A' && duplicate) return [];

return [{
  json: {
    _path: path,
    _dedupe_key: key,
    _duplicate: duplicate,
    _rate_this_hour: rateThisHour,
    _rate_exceeded: rateExceeded,
    _ledger_size: Object.keys(sd.seen).length,
    body: raw,
  },
}];
