// BuildErrorContext — recover what can be recovered from a failed run.
//
// Reached from any error branch on either path. It must work when almost
// nothing else did, so it depends on as little as possible: CONFIG, whatever
// ids could be salvaged, and the error itself.
//
// v5 called this BuildErrorPatch and it built a patch marking the organization
// as Errored. v6 writes NOTHING to the organization on failure. A field that
// says "Error" is a field a rep learns to ignore, and it is indistinguishable
// from a real judgement about the company. The failure goes where failures
// belong: one Slack alert, one activity saying the run failed, and the audit
// row with the detail.
//
// It never throws. It is the last line of the error path, and throwing here
// would lose the Slack alert as well.

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
// @@VALIDATOR@@

const item = $input.first().json || {};

// The error and the ids come from whichever upstream node got far enough. In
// n8n an error branch carries the failing item plus an `error` property.
const error = item.error || {};
const errorName = error.name || item.error_name || 'IcpUnknownError';
const errorMessage = String(error.message || item.error_message || 'unknown error').slice(0, 500);
let problems = Array.isArray(error.problems) ? error.problems : (item.problems || []);

const first = (...values) => {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return null;
};

// ---------------------------------------------------------------------------
// Read the ORIGINAL request back off the webhook, not off the error.
//
// This is not belt and braces, it is the only thing that works. n8n's task
// runner does not carry a thrown error's own properties across an error
// output: execution 60629 threw an IcpMalformedEvent with `.problems` and
// `.org_id` set, and what arrived here was `IcpUnknownError`, zero problems,
// org_id null — so the failure activity was posted with no organization at
// all and landed nowhere, which is the definition of dying quietly.
//
// The webhook node is upstream on either path and its item is intact
// whatever failed downstream, so the ids come from there. Wrapped, because
// `$('X')` throws when X is not connected upstream and each path has only
// one of these two.
// ---------------------------------------------------------------------------
let received = {};
try { received = $('Webhook Clay').item.json.body || {}; } catch (e) { received = {}; }
if (!received || Object.keys(received).length === 0) {
  try { received = $('Webhook Pipedrive').item.json.body || {}; } catch (e) { received = received || {}; }
}
const receivedMeta = received.meta || {};

const body = item.body || {};
const requestId = first(item.request_id, body.request_id, error.request_id, received.request_id);
const orgId = first(item.org_id, body.org_id, error.org_id, received.org_id, (received.data || {}).org_id);
const dealId = first(item.deal_id, body.deal_id, received.deal_id, receivedMeta.entity_id);

// ---------------------------------------------------------------------------
// Recover the problem list by RE-VALIDATING, not by reading the error.
//
// Two cheaper routes were tried first and neither survives the task runner.
// The thrown error's `.problems` array is dropped crossing the error output,
// and so is its message — 60648 arrived here as "unknown error" — so there is
// nothing to parse. What IS intact is the body the webhook received, and the
// validator is deterministic, so running it again produces exactly the list
// the boundary rejected the event for.
//
// This is why the node is generated: it carries the same
// engine/validate_event.mjs that ParseScored does, so the reason given in
// Slack is the reason the event was actually refused, not a second opinion.
// ---------------------------------------------------------------------------
let problems_source = 'error';
if (problems.length === 0 && received && Object.keys(received).length > 0) {
  try {
    const revalidated = validateEvent(received, cfg);
    if (revalidated.length > 0) {
      problems = revalidated;
      problems_source = 'revalidated';
    }
  } catch (e) {
    // A validator that throws on a payload this strange is not worth losing
    // the alert over. The message and the ids still get through.
  }
}
// Last resort: the message, when it did survive, formats them as "...: a; b; c".
if (problems.length === 0 && errorMessage.indexOf('ICP_MALFORMED_EVENT') !== -1) {
  const tail = errorMessage.slice(errorMessage.indexOf(':', errorMessage.indexOf('ICP_MALFORMED_EVENT')) + 1);
  problems = tail.split(';').map((p) => p.trim()).filter((p) => p !== '');
  problems_source = 'message';
}

// ---------------------------------------------------------------------------
// Forget this request, so a corrected redelivery is not dropped as a duplicate.
//
// Dedupe writes the key to the ledger on RECEIPT, before anything downstream
// has had a chance to reject the payload. So a run that failed validation has
// already claimed its request_id, and when Clay re-sends the same row after the
// table is fixed, Dedupe sees the key, calls it a duplicate and skips the
// write — silently, and for 48 hours.
//
// A run that failed did not happen. Removing the key here is what makes that
// true: the ledger's job is "do not score the same request twice", and this
// request was never scored.
// ---------------------------------------------------------------------------
let forgot = null;
try {
  // The error branch carries the failing INPUT item, which on Path B is
  // Dedupe B's output and already holds the key. The named lookup is the
  // fallback for the branches where it does not.
  let key = item._dedupe_key || null;
  if (!key) { try { key = $('Dedupe B').item.json._dedupe_key; } catch (e) { key = null; } }
  if (key) {
    const sd = $getWorkflowStaticData('global');
    if (sd && sd.seen && Object.prototype.hasOwnProperty.call(sd.seen, key)) {
      delete sd.seen[key];
      forgot = key;
    }
  }
} catch (e) {
  forgot = null;
}

return [{
  json: {
    request_id: requestId,
    // Named so a reader can tell "this request may be retried" from "this one
    // is still claimed", without reading the ledger.
    dedupe_key_released: forgot,
    org_id: orgId,
    deal_id: dealId,
    error_name: errorName,
    error_message: errorMessage,
    // Every schema violation at once, so one read of the audit row is enough
    // to fix the table rather than one round trip per problem.
    problems: problems.slice(0, 20),
    problem_count: problems.length,
    // Where the list came from, because "the error said so" and "we ran the
    // validator again" are different levels of evidence.
    problems_source: problems.length > 0 ? problems_source : 'none',
    // Stated so the audit row and any reader can see it as a fact rather than
    // having to infer it from the absence of a PATCH node in the trace.
    org_untouched: true,
    // What actually arrived, capped. A malformed event is diagnosed from the
    // payload, and by the time anyone looks the Clay row may have been rerun.
    received_keys: Object.keys(received).slice(0, 40),
    model_version: cfg.model_version,
  },
}];
