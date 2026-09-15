// BuildErrorPatch — mark the organization as Errored, idempotently.
//
// Reached from any error branch on either path. It must work when almost
// nothing else did, so it depends on as little as possible: CONFIG, whatever
// org id could be recovered, and the org record if one was fetched.
//
// Idempotent the same way BuildOrgPatch is: if ICP Calculated already says
// Error, the patch is {} and the IF gate skips the PATCH. A Clay outage
// retrying for an hour writes "Error" exactly once.

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

const requestId = item.request_id || (item.body && item.body.request_id) || null;
const orgId = item.org_id || (item.body && item.body.org_id) || null;
const dealId = item.deal_id || (item.body && item.body.deal_id) || null;

const org = item.organization || item.data || {};
const existing = org.custom_fields || {};

const optionId = cfg.opt_icp_calculated[cfg.label_error];
if (optionId === null || optionId === undefined) {
  // Do NOT throw here. This node is the last line of the error path, and
  // throwing would lose the Slack alert as well as the mark. Emit a patch that
  // the gate will skip, and say why.
  return [{
    json: {
      request_id: requestId,
      org_id: orgId,
      deal_id: dealId,
      patch: {},
      patch_is_empty: true,
      changed_fields: [],
      error_name: errorName,
      error_message: errorMessage,
      degraded: `no option id for "${cfg.label_error}" in CONFIG — org not marked; ` +
                `run pipedrive_create_fields and npm run gen:config`,
    },
  }];
}

const same = (a, b) => {
  if (a === null || a === undefined) return b === null || b === undefined;
  if (b === null || b === undefined) return false;
  return String(a) === String(b);
};

const alreadyErrored = same(existing[cfg.f_icp_calculated], optionId);

const customFields = {};
const changed = [];
if (!alreadyErrored) {
  customFields[cfg.f_icp_calculated] = optionId;
  changed.push(cfg.f_icp_calculated);
}

// The model version and the date are recorded on an error too: without them,
// the idempotency gate cannot tell "errored today on v5" from "never scored",
// and would retry the same failing org on every deal.
const scoredAt = String(cfg.now_iso).slice(0, 10);
if (!same(existing[cfg.f_icp_scored_at], scoredAt)) {
  customFields[cfg.f_icp_scored_at] = scoredAt;
  changed.push(cfg.f_icp_scored_at);
}
if (!same(existing[cfg.f_icp_model_version], cfg.model_version)) {
  customFields[cfg.f_icp_model_version] = cfg.model_version;
  changed.push(cfg.f_icp_model_version);
}

for (const forbidden of cfg.fields_never_write || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, forbidden)) {
    throw new Error(`ICP_FORBIDDEN_WRITE: error patch contains ${forbidden}`);
  }
}

return [{
  json: {
    request_id: requestId,
    org_id: orgId,
    deal_id: dealId,
    patch: changed.length === 0 ? {} : { custom_fields: customFields },
    patch_is_empty: changed.length === 0,
    changed_fields: changed,
    target_label: cfg.label_error,
    target_option_id: optionId,
    scored_at: scoredAt,
    error_name: errorName,
    error_message: errorMessage,
    execution_id: $execution.id,
  },
}];
