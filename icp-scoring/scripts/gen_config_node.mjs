#!/usr/bin/env node
// scripts/gen_config_node.mjs — write n8n/nodes/CONFIG.json.
//
// CONFIG is the one node that holds every id, key, option id, window and
// rubric constant. Because it is generated from config/rubric_v5.json and
// config/pipedrive_fields.json, a field key or a threshold cannot be typed
// into a node by hand — which is what makes the static test "no literal
// Pipedrive field hashes outside CONFIG" enforceable rather than aspirational.
//
// Run: npm run gen:config   (after every pipedrive_create_fields run)
//
// The four environment-specific values are NOT in this file. A Clay webhook
// URL is an unguessable endpoint, so it is a secret, and invariant 1 forbids
// secrets in any file. They are spliced into the Set node's jsonOutput
// expression from $env at runtime:
//     ICP_CLAY_WEBHOOK_URL, ICP_CLAY_CALLBACK_URL,
//     ICP_AUDIT_SHEET_ID,   ICP_SLACK_CHANNEL

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v5.json'), 'utf8'));
const FIELDS = JSON.parse(readFileSync(join(ROOT, 'config', 'pipedrive_fields.json'), 'utf8'));

export const ENV_KEYS = {
  clay_webhook_url: 'ICP_CLAY_WEBHOOK_URL',
  clay_callback_url: 'ICP_CLAY_CALLBACK_URL',
  audit_sheet_id: 'ICP_AUDIT_SHEET_ID',
  slack_channel_ops: 'ICP_SLACK_CHANNEL',
};

const field = (slug) => {
  const entry = FIELDS.fields[slug];
  if (!entry) throw new Error(`config/pipedrive_fields.json has no field "${slug}"`);
  if (!entry.key) throw new Error(`field "${slug}" has no key — run pipedrive_create_fields`);
  return entry.key;
};

const options = (slug) => {
  const entry = FIELDS.fields[slug];
  const out = {};
  for (const [label, option] of Object.entries(entry.options || {})) {
    // A placeholder registry has null ids. Keep the shape so CONFIG is
    // structurally complete and the static tests can run; a live run fills
    // them in. BuildOrgPatch refuses to write a null option id.
    out[label] = option.id;
  }
  return out;
};

export function buildConfig() {
  return {
    // --- provenance ------------------------------------------------------
    _generated_by: 'scripts/gen_config_node.mjs',
    _sources: ['config/rubric_v5.json', 'config/pipedrive_fields.json'],
    _field_registry_status: FIELDS.status,

    // --- rubric constants ------------------------------------------------
    model_version: RUBRIC.model_version,
    levels: RUBRIC.levels,
    weights: RUBRIC.weights,
    thresholds: RUBRIC.thresholds,
    grade_labels: RUBRIC.grade_labels,
    activation_multipliers: RUBRIC.activation_multipliers,
    activation_default: RUBRIC.activation_default_when_no_evidence,
    contracting_max_age_months: RUBRIC.activation_contracting_evidence_max_age_months,
    insufficient_components: RUBRIC.insufficient_data_rule.components,
    tier2_rule: RUBRIC.tier2_flag_rule,
    // BuildNote prints the level text for each component; it comes from the
    // rubric, not from a string in the node.
    component_scales: RUBRIC.component_scales,
    vertical_tier: Object.fromEntries(
      Object.entries(RUBRIC.industry_verticals).map(([name, row]) => [name, row.tier])
    ),

    // --- Pipedrive field keys --------------------------------------------
    f_icp_calculated: field('icp_calculated'),
    f_icp_score: field('icp_score'),
    f_icp_scored_at: field('icp_scored_at'),
    f_icp_model_version: field('icp_model_version'),
    // Present so BuildOrgPatch can assert it never writes it, and so the
    // static test can check the key by name rather than by literal.
    f_icp_final: field('icp_final'),
    fields_never_write: [field('icp_final')],

    // --- Pipedrive enum option ids ---------------------------------------
    opt_icp_calculated: options('icp_calculated'),
    label_insufficient: 'Insufficient data',
    label_error: 'Error',

    // --- policy ----------------------------------------------------------
    rescore_after_days: RUBRIC.rescore_after_days,
    // Deviation on record: §8.1 says skip when ICP Calculated is present at
    // all. Skipping for 180 days because a previous run hit a transient error
    // would be a bug, not idempotency, so only a real grade counts as a fresh
    // score. Set false to follow §8.1 literally.
    rescore_on_error_or_insufficient: true,
    dedupe_ttl_hours: 48,
    // Anomaly gate: a bulk import creating thousands of deals would otherwise
    // fan out into thousands of Clay credits before anyone noticed. Warns as a
    // non-blocking tee; never blocks the spine.
    max_events_per_hour: 200,
    note_max_chars: 1500,

    // --- expected shapes -------------------------------------------------
    trigger_entity: 'deal',
    trigger_action: 'create',
    clay_event_name: 'icp.scored',
  };
}

export const CONFIG_PRETTY = `${JSON.stringify(buildConfig(), null, 2)}\n`;

// Write ONLY when run directly, so a test that imports buildConfig() to check
// n8n/nodes/CONFIG.json for staleness does not refresh it first.
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const config = buildConfig();
  const pretty = `${JSON.stringify(config, null, 2)}\n`;
  writeFileSync(join(ROOT, 'n8n', 'nodes', 'CONFIG.json'), pretty, 'utf8');
  process.stdout.write(
    `wrote n8n/nodes/CONFIG.json (${pretty.length} bytes, ${Object.keys(config).length} keys)\n` +
    `  field registry status: ${FIELDS.status}\n` +
    `  env-sourced at runtime: ${Object.values(ENV_KEYS).join(', ')}\n`
  );
}
