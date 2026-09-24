// FailLoudly — the last node on the error branch, and the whole reason the
// branch is allowed to exist.
//
// The bug this fixes, precisely:
//
//   ParseScored has onError: continueErrorOutput, so a rejected event flows
//   down the error branch instead of stopping the run. The branch alerts and
//   posts an activity, and then the execution ENDS — as a SUCCESS, because
//   nothing threw. n8n only runs settings.errorWorkflow when an execution ends
//   in error, so WF-ERR never fired. Path B had answered Clay 200, written
//   nothing, and told nobody. Execution 60629 is that, exactly.
//
// So the branch now ends by throwing. The alert and the activity have already
// happened by the time this runs — it is wired last on purpose — and the throw
// costs nothing except the thing it buys: the execution goes red, WF-ERR picks
// it up, and it reaches Slack through the alerting the rest of the stack
// already uses.
//
// A 200 ack followed by a silent failure is invisible to Clay: the table has
// no idea the row was rejected, and will not resend. Red executions are the
// only signal that crosses that gap.

// Read BuildErrorContext BY NAME. This node is wired last, so its $json is
// whatever the Pipedrive activity call returned — not the failure context.
let item = {};
try { item = $('BuildErrorContext').item.json || {}; } catch (e) { item = $input.first().json || {}; }

const name = item.error_name || 'IcpUnknownError';
const message = item.error_message || 'unknown error';
const problems = Array.isArray(item.problems) ? item.problems : [];

const parts = [
  `${name}: ${message}`,
  `org_id=${item.org_id === null || item.org_id === undefined ? '(none)' : item.org_id}`,
  `request_id=${item.request_id || '(none)'}`,
];
if (problems.length > 0) {
  parts.push(`${problems.length} problem(s): ${problems.join('; ')}`);
}
// Said plainly, because this string is what lands in Slack via WF-ERR and it
// is read by someone who has not opened the execution yet.
parts.push('the organization was not written to; Clay was answered 200 and does not know');

const error = new Error(`ICP_RUN_FAILED — ${parts.join(' | ')}`);
error.name = 'IcpRunFailed';
throw error;
