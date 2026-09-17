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
const item = $input.first().json || {};

// The error and the ids come from whichever upstream node got far enough. In
// n8n an error branch carries the failing item plus an `error` property.
const error = item.error || {};
const errorName = error.name || item.error_name || 'IcpUnknownError';
const errorMessage = String(error.message || item.error_message || 'unknown error').slice(0, 500);
const problems = Array.isArray(error.problems) ? error.problems : (item.problems || []);

const first = (...values) => {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return null;
};

const body = item.body || {};
const requestId = first(item.request_id, body.request_id, error.request_id);
const orgId = first(item.org_id, body.org_id, error.org_id);
const dealId = first(item.deal_id, body.deal_id);

return [{
  json: {
    request_id: requestId,
    org_id: orgId,
    deal_id: dealId,
    error_name: errorName,
    error_message: errorMessage,
    // Every schema violation at once, so one read of the audit row is enough
    // to fix the table rather than one round trip per problem.
    problems: problems.slice(0, 20),
    problem_count: problems.length,
    // Stated so the audit row and any reader can see it as a fact rather than
    // having to infer it from the absence of a PATCH node in the trace.
    org_untouched: true,
    model_version: cfg.model_version,
  },
}];
