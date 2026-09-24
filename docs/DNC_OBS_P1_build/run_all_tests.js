'use strict';
// Master static-test runner for the DNC/observability build. Run: node run_all_tests.js
const { execFileSync } = require('child_process');
const path = require('path');
const suites = [
  'subworkflows/tests/dnc_contract_tests.js',
  'workflows/heyreach_reply_to_dnc_ledger/tests/tee_tests.js',
  'workflows/dnc_expiry_job/tests/expiry_tests.js',
  'workflows/smartlead_observability_readonly/tests/obs_tests.js',
  'workflows/dnc_check_service/tests/check_tests.js',
];
let failed = 0;
for (const s of suites) {
  console.log('\n=== ' + s + ' ===');
  try { console.log(execFileSync('node', [path.join(__dirname, s)], { encoding: 'utf8' })); }
  catch (e) { failed++; console.log((e.stdout || '') + (e.stderr || '')); console.log('SUITE FAILED: ' + s); }
}
console.log('\n===== ' + (failed ? failed + ' SUITE(S) FAILED' : 'ALL SUITES PASSED') + ' =====');
process.exit(failed ? 1 : 0);
