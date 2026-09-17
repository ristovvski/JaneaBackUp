#!/usr/bin/env node
// scripts/gen_config_node.mjs — write n8n/nodes/CONFIG.json.
//
// CONFIG is the one node that holds every id, key, option id, window and
// rubric constant. Because it is generated from config/rubric_v6.json and
// config/pipedrive_fields.json, a field key or a threshold cannot be typed
// into a node by hand — which is what makes the static test "no literal
// Pipedrive field hashes outside CONFIG" enforceable rather than aspirational.
//
// Run: npm run gen:config   (after every pipedrive_create_fields run)
//
// The three environment-specific values are NOT in this file. A Clay webhook
// URL is an unguessable endpoint, so it is a secret, and invariant 1 forbids
// secrets in any file. They are spliced into the Set node's jsonOutput
// expression from $env at runtime:
//     ICP_CLAY_ENGINE_URL, ICP_CLAY_CALLBACK_URL, ICP_SLACK_CHANNEL

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v6.json'), 'utf8'));
// Prefer the live registry a create_fields run produced; fall back to the
// committed placeholder template so a fresh clone can still build and test.
const FIELDS_LOCAL = join(ROOT, 'config', 'pipedrive_fields.local.json');
const FIELDS_TEMPLATE = join(ROOT, 'config', 'pipedrive_fields.json');
const FIELDS_PATH = existsSync(FIELDS_LOCAL) ? FIELDS_LOCAL : FIELDS_TEMPLATE;
const FIELDS = JSON.parse(readFileSync(FIELDS_PATH, 'utf8'));

// Three values, not four. The audit store moved from a Google Sheet to an n8n
// Data Table, and a table NAME is neither a secret nor environment-specific —
// it is a plain constant below. `clay_engine_url` is the v6 name for what v5
// called clay_webhook_url: it now points at the ICP table's webhook source
// rather than at the retired Clay Workflow trigger.
export const ENV_KEYS = {
  clay_engine_url: 'ICP_CLAY_ENGINE_URL',
  clay_callback_url: 'ICP_CLAY_CALLBACK_URL',
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
    _sources: ['config/rubric_v6.json', 'config/pipedrive_fields.json'],
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
    // vertical -> level, resolved through the tier map here rather than in the
    // node. ParseScored checks the posted industry level against this, which is
    // how a stale vertical map in the Clay table gets caught at the boundary
    // instead of quietly grading an Anchor account as Opportunistic.
    vertical_level: Object.fromEntries(
      Object.entries(RUBRIC.industry_verticals).map(([name, row]) => {
        const level = RUBRIC.industry_vertical_map[row.tier];
        if (level === undefined) {
          throw new Error(`rubric: vertical "${name}" has tier "${row.tier}", absent from industry_vertical_map`);
        }
        return [name, level];
      })
    ),

    // --- Pipedrive field keys --------------------------------------------
    // v6 writes ONE organization field. Everything else a run produces —
    // composite, levels, multiplier, the activation guard, the whole trace —
    // goes to icp_audit, where it can be queried without adding a column to a
    // CRM record that a rep has to read past.
    f_auto_icp_score: field('auto_icp_score'),

    // Never written. Present so BuildOrgPatch can ASSERT it is absent from
    // every patch rather than merely omitting it, and so the static suite can
    // name the key without a literal.
    f_sales_rep_icp_score: field('sales_rep_icp_score'),
    f_icp_final: field('icp_final'),
    fields_never_write: [field('sales_rep_icp_score'), field('icp_final')],

    // The four v5 fields, retained ONLY so the static suite can assert no
    // patch ever contains them. They still exist in the account; whether they
    // are deleted is Nik's call.
    f_retired_v5: [
      field('icp_calculated'), field('icp_score'),
      field('icp_scored_at'), field('icp_model_version'),
    ],

    // --- the one written value -------------------------------------------
    // "56 - B". One string, one meaning, and a rep can read it without a
    // legend. The insufficient form deliberately keeps the same shape so a
    // column of these sorts and filters as one thing.
    auto_score_separator: ' - ',
    label_insufficient: 'n/a - insufficient data',
    label_error: 'n/a - error',

    // --- the activity ----------------------------------------------------
    // One per scoring run, marked done so it lands as a record rather than as
    // a task in someone's queue. `task` is the generic type this account
    // actually uses (meeting/email/qualify/renewal/task are the live ones);
    // Pipedrive has no "note" activity type.
    activity_type: 'task',
    activity_subject: 'ICP scored',
    activity_max_chars: 900,

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
    // The n8n Data Table the audit row is appended to. A name, not an id: the
    // Data Table node resolves either, and a name survives a table being
    // recreated in a way an id does not.
    audit_data_table: 'icp_audit',

    trigger_entity: 'deal',
    trigger_action: 'create',
    clay_event_name: 'icp.scored',
  };
}

export const CONFIG_PRETTY = `${JSON.stringify(buildConfig(), null, 2)}\n`;

// Where the rendering goes depends on whether it carries real field keys.
//
//   template registry -> n8n/nodes/CONFIG.json        (committed, placeholders)
//   live registry     -> n8n/nodes/CONFIG.local.json  (gitignored, real 40-hex keys)
//
// A real Pipedrive field key is not a credential, but it is an account
// identifier and the owner's rule is that nothing key-shaped reaches git. The
// patcher and the test harness both prefer the .local.json when it exists, so
// a machine that has run create_fields builds the real workflow while a fresh
// clone still builds and tests from the placeholders.
export const USING_LIVE_REGISTRY = FIELDS_PATH.endsWith('.local.json');
export const CONFIG_OUT = join(
  ROOT, 'n8n', 'nodes', USING_LIVE_REGISTRY ? 'CONFIG.local.json' : 'CONFIG.json'
);

// Write ONLY when run directly, so a test that imports buildConfig() to check
// the rendering for staleness does not refresh it first.
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const config = buildConfig();
  const pretty = `${JSON.stringify(config, null, 2)}\n`;
  writeFileSync(CONFIG_OUT, pretty, 'utf8');
  process.stdout.write(
    `wrote n8n/nodes/${USING_LIVE_REGISTRY ? 'CONFIG.local.json' : 'CONFIG.json'} ` +
    `(${pretty.length} bytes, ${Object.keys(config).length} keys)\n` +
    `  field registry: ${USING_LIVE_REGISTRY ? 'LIVE (.local.json, real field keys)' : 'placeholder template'}, status=${FIELDS.status}\n` +
    `  env-sourced at runtime: ${Object.values(ENV_KEYS).join(', ')}\n` +
    (USING_LIVE_REGISTRY
      ? '  this rendering is gitignored; the committed CONFIG.json stays the placeholder\n'
      : '')
  );
}
