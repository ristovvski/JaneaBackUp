#!/usr/bin/env node
/**
 * clay/build_workflow.mjs — build the `ICP_Engine` Clay Workflow from this repo.
 *
 * The workflow is the same contract as engine/clay_table_spec.md, expressed with
 * the Workflow primitive instead of a table: webhook in from n8n Path A,
 * enrichment waterfall, seven classifiers, the v5 score, `icp.scored` out to
 * n8n Path B. Everything it needs comes from tracked sources — the seven prompt
 * files, the three schemas, config/rubric_v5.json and the parity-tested Python
 * scorer — so a rubric change is a regenerate-and-rerun, not a UI safari.
 *
 * Idempotent: nodes are matched to the live graph BY NAME, so re-running
 * updates in place rather than duplicating. It never deletes a node it did not
 * create, and it never publishes: publishing is what takes the Path A trigger
 * live, and that is the user's call.
 *
 * Usage:
 *   node clay/build_workflow.mjs --workflow wf_xxx [--dry-run] [--model <id>]
 *
 * Requires the `clay` CLI on PATH, already signed in to the target workspace.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const argv = process.argv.slice(2);
const arg = (name, fallback = null) => {
  const i = argv.indexOf(`--${name}`);
  return i === -1 ? fallback : argv[i + 1];
};
const WORKFLOW_ID = arg('workflow', process.env.ICP_CLAY_WORKFLOW_ID);
const DRY_RUN = argv.includes('--dry-run');

/**
 * Model policy: OpenAI only, on the workspace's own key.
 *
 * Classification runs on Sol, summarization on Terra. Luna is excluded by
 * policy, and so is every Clay-native Claygent model — which is why not one
 * node in this graph is `nodeType: "agent"`. Both ids were confirmed present on
 * the key with GET /v1/models and callable with strict structured outputs.
 *
 * NOTE ON TEMPERATURE. The rubric asks for temperature 0. The GPT-5.6 family
 * refuses it outright:
 *
 *   HTTP 400 — "Unsupported value: 'temperature' does not support 0 with this
 *   model. Only the default (1) value is supported."
 *
 * So no request here sends `temperature`; a fixed `seed` and a closed
 * strict-mode schema are what stand in for it. That is weaker than temperature
 * 0 and it is recorded as such in clay/WORKFLOW.md, not papered over.
 */
export const MODELS = {
  classifier: arg('classifier-model', 'gpt-5.6-sol'),
  summary: arg('summary-model', 'gpt-5.6-terra'),
};

// Excluded by policy. Named so that a typo or a copy-paste cannot quietly
// reintroduce one.
const FORBIDDEN_MODELS = [/luna/i, /^claude-/i, /^gpt-5\.4-nano$/i];
for (const [role, model] of Object.entries(MODELS)) {
  const banned = FORBIDDEN_MODELS.find((re) => re.test(model));
  if (banned) throw new Error(`model policy: ${role} model "${model}" is excluded (${banned})`);
}

const OPENAI_URL = 'https://api.openai.com/v1/chat/completions';

if (!WORKFLOW_ID && process.argv[1] && process.argv[1].endsWith('build_workflow.mjs')) {
  console.error('usage: node clay/build_workflow.mjs --workflow wf_xxx');
  process.exit(2);
}

// ---------------------------------------------------------------------------
// clay CLI plumbing
// ---------------------------------------------------------------------------

const TMP = mkdtempSync(join(tmpdir(), 'icp-clay-'));
let calls = 0;

function clay(args, payload) {
  calls += 1;
  const full = [...args];
  if (payload !== undefined) {
    const file = join(TMP, `payload-${calls}.json`);
    writeFileSync(file, JSON.stringify(payload, null, 2));
    full.push('--input', file);
  }
  if (DRY_RUN && args.some((a) => a === 'create' || a === 'update')) {
    return { dryRun: true, args: full };
  }

  // A build is ~80 CLI calls and any one of them can time out on the way to
  // Clay. Without a retry the whole build dies half-applied, which is worse
  // than slow: the canvas is then a mix of old and new nodes. Retried only for
  // transport failures — a validation_error is a bug in this script and must
  // surface on the first attempt, not five times over.
  const TRANSIENT = /network_error|network_timeout|rate_limited|timed out|ECONNRESET|ETIMEDOUT|EAI_AGAIN|502|503|504/i;
  let lastError;
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    try {
      return JSON.parse(execFileSync('clay', full, {
        encoding: 'utf8',
        maxBuffer: 64 * 1024 * 1024,
      }));
    } catch (error) {
      lastError = error;
      const text = `${error.stdout ?? ''}${error.stderr ?? ''}${error.message ?? ''}`;
      if (!TRANSIENT.test(text) || attempt === 4) throw error;
      const waitMs = 2000 * (2 ** (attempt - 1));   // 2s, 4s, 8s
      console.error(`  .. ${args.slice(0, 3).join(' ')} — transient failure, retrying in ${waitMs / 1000}s`);
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, waitMs);
    }
  }
  throw lastError;
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

const RUBRIC = JSON.parse(read('config/rubric_v5.json'));
const PREAMBLE = read('engine/prompts/_preamble.md');
const SCORER = read('engine/clay_score.py');

const VERTICALS = Object.keys(RUBRIC.industry_verticals ?? {});
if (VERTICALS.length !== 17) {
  throw new Error(`expected 17 verticals in config/rubric_v5.json, found ${VERTICALS.length}`);
}
const ACTIVATION_STATES = Object.keys(RUBRIC.activation_multipliers ?? {});
if (ACTIVATION_STATES.length !== 4) {
  throw new Error(`expected 4 activation states, found ${ACTIVATION_STATES.length}`);
}
const LEVELS = RUBRIC.levels.map(String);

// Clay renders a `select` field's choices from a JSON STRING of {text} objects.
const options = (values) => JSON.stringify(values.map((text) => ({ text: String(text) })));

// ---------------------------------------------------------------------------
// Action catalog — packageId/actionKey pairs, from `clay workflows actions list`
// ---------------------------------------------------------------------------

const PKG = {
  cpj: 'e251a70e-46d7-4f3a-b3ef-a211ad3d8bd2',
  clay: '4299091f-3cd3-4d68-b198-0143575f471d',
  apollo: '778df10d-f68b-461a-8eb7-56047737f5eb',
  predictleads: 'aa68bb13-b114-404a-a5cf-f920e72fbc90',
  pdl: '78593846-c4d6-481c-94bf-76b7912cf94d',
};

const tool = (actionPackageId, actionKey, inputMappingConfig) => [
  { toolType: 'clay_action', actionKey, actionPackageId, inputMappingConfig },
];

const ref = (expression) => ({ type: 'reference', expression });
const fixed = (value) => ({ type: 'static', value });
const item = (path = '$') => ({ type: 'item', path });

/**
 * Every provider node runs in LIST MODE over a one-element list.
 *
 * Not for fan-out — for survivability. A Clay tool node has no
 * continue-on-error: when its action fails, the run fails and nothing
 * downstream executes, so one provider outage loses the entire score. The only
 * documented escape hatch is `listFailureMode: "ignore_errors"`, which is a
 * list-mode setting. Running the single call as a list of one buys that
 * behaviour, and the run degrades to "that fact is null" — which is exactly
 * what the table does when an enrichment column errors.
 *
 * The cost is the output shape: a list-mode node's results are an array at
 * `$.results`, so downstream reads `$.results[0].<field>` instead of
 * `$.result.<field>`.
 */
const resilient = (listSource, listPath) => ({
  listMode: true,
  listFailureMode: 'ignore_errors',
  listEntriesRef: { __fromRef: listSource, path: listPath },
});
const FROM_IDENTIFIER = ['01 Prepare enrichment inputs', '$.identifier_list'];
const FROM_DOMAIN = ['04 Resolve domain for enrichment', '$.domain_list'];

// ---------------------------------------------------------------------------
// Pinned inputs. `sourceNodeId` is filled in on the second pass, once every
// node has a real id — hence the node NAME here and the resolve step below.
// ---------------------------------------------------------------------------

const pin = (fromNodeName, sourcePath, type = 'string') => ({
  __from: fromNodeName,
  sourcePath,
  type,
});

const properties = (map) => ({ type: 'object', properties: map });

// The Path A webhook contract. `openai_api_key` is the one addition to
// clay_table_spec.md's twelve keys, and it is not cosmetic: Clay has no
// CLI-reachable secret store and a code node has no egress, so the only way an
// OpenAI-only model policy can run inside Clay without committing a key to this
// repository is for n8n to send it from its own credential store, per request.
// Flagged in clay/WORKFLOW.md as a contract change, not slipped in.
export const WEBHOOK_KEYS = [
  'request_id', 'org_id', 'deal_id', 'identifier_kind', 'identifier_value',
  'domain', 'linkedin_url', 'company_name', 'hq_country', 'hq_state',
  'model_version', 'callback_url', 'openai_api_key',
];

const TRIGGER = '__trigger__';

// ---------------------------------------------------------------------------
// The seven classifiers — prompts and strict schemas
// ---------------------------------------------------------------------------

export const COMPONENTS = [
  ['industry_vertical', 'industry vertical'],
  ['stage_maturity', 'stage maturity'],
  ['company_type', 'company type'],
  ['geography', 'geography'],
  ['revenue_range', 'revenue range'],
  ['activation_state', 'activation state'],
  ['buying_signal', 'buying signal'],
];

const stripHtmlComment = (text) => text.replace(/<!--[\s\S]*?-->\n*/, '').trim();

/**
 * The system prompt for one classifier: the shared preamble, the component's
 * own rules, and the two limits the strict schema cannot carry.
 *
 * `facts_json` is NOT interpolated here. It goes in the user message, built at
 * run time by clay/code/15_build_classifier_requests.py, so the system prompt
 * is identical on every request and stays cacheable.
 */
export function classifierPrompt(component) {
  return [
    stripHtmlComment(PREAMBLE),
    '',
    stripHtmlComment(read(`engine/prompts/${component}.md`)),
    '',
    '---',
    '',
    '## Two limits your output schema cannot express',
    '',
    'Your reply is validated against a strict JSON schema, so `value`, `confidence`',
    'and the key set are already closed. Two things in the contract are not',
    'expressible there and are therefore on you:',
    '',
    '- `evidence`: **at most 6 items**, each **under 200 characters**.',
    '- `missing_inputs`: name only the fact keys you actually needed.',
    '',
    `The component you are classifying is \`${component}\`. Nothing else.`,
  ].join('\n');
}

export const STRICT_SCHEMAS = Object.fromEntries(
  COMPONENTS.map(([component]) => [
    component,
    // read() returns TEXT. Embedding it unparsed shipped the schema to OpenAI
    // as a JSON *string* instead of an object, and the API answered
    // ERROR_ACTION_RUNTIME_ERROR. Parse it.
    JSON.parse(read(`engine/schemas/openai/${component}.strict.json`)),
  ]),
);

/**
 * A Python expression that evaluates to `value`, exactly.
 *
 * Not a hand-rolled dict literal. The obvious version — JSON.stringify then
 * s/true/True/, s/null/None/ — is textual, so it also rewrites those words
 * INSIDE string values. The classifier preamble contains the sentence "set
 * `value` to `null`", and that version silently turned it into "set `value` to
 * `None`": a prompt that no longer matches engine/prompts/_preamble.md, shipped
 * with a green build.
 *
 * `json.loads` of a JSON string has neither problem. JSON.stringify's escaping
 * (\", \\, \n, \uXXXX) is a subset of Python's, so its output is also a valid
 * Python string literal.
 */
const pythonJson = (value) => `json.loads(${JSON.stringify(JSON.stringify(value, null, 2))})`;

/**
 * Inline the prompts and schemas into node 15's Python.
 *
 * A Clay code node cannot read this repository at run time, so the only way the
 * canvas can be provably identical to `engine/prompts/*.md` and
 * `engine/schemas/openai/*.strict.json` is to generate them in and diff the
 * whole node body on every build. Pass 3 does that diff.
 */
export function classifierRequestCode() {
  const prompts = Object.fromEntries(
    COMPONENTS.map(([component]) => [component, classifierPrompt(component)]),
  );
  return read('clay/code/16_build_classifier_requests.py')
    .replace('@@CLASSIFIER_MODEL@@', MODELS.classifier)
    .replace(
      '# @@GENERATED@@',
      [
        '# --- GENERATED by clay/build_workflow.mjs from engine/prompts/*.md ---',
        `PROMPTS = ${pythonJson(prompts)}`,
        '',
        '# --- GENERATED from engine/schemas/openai/*.strict.json ---',
        `SCHEMAS = ${pythonJson(STRICT_SCHEMAS)}`,
      ].join('\n'),
    );
}

// ---------------------------------------------------------------------------
// OpenAI calls are tool nodes, not agent nodes
//
// A Clay code node has no network egress at all: `urllib` is not importable and
// the node runtime exposes no `context.call_tool` (both measured — see
// clay/WORKFLOW.md). So every LLM call goes through `http-api-v2`, with a code
// node either side to build the body and read the reply.
//
// The API key is never embedded. It is referenced from `openai_api_key`, which
// arrives in the Path A webhook payload and is pinned through node 01 — so the
// key lives in n8n's credential store and nowhere in this repository.
// ---------------------------------------------------------------------------

function openAiNode({ name, bodyFrom, bodyPath, after }) {
  return {
    name,
    spec: {
      nodeType: 'tool',
      name,
      // ONLY the action's own parameters may appear here. A property of our own
      // — `openai_api_key`, say — is not "silently dropped on save" as the docs
      // state: it persists, and the action then throws
      // ERROR_ACTION_RUNTIME_ERROR at run time with no status and no message.
      // That cost several runs to find. The key rides inside `headers`, which
      // IS an action parameter, built by the code node upstream.
      inputSchema: properties({
        body: pin(bodyFrom, bodyPath),
        headers: pin(bodyFrom, '$.headers', 'object'),
      }),
      tools: tool(PKG.clay, 'http-api-v2', {
        method: fixed('POST'),
        url: fixed(OPENAI_URL),
        body: ref('{{body}}'),
        // `headers` is deliberately ABSENT from this mapping. It is supplied by
        // the pin above and nothing else. An object-valued action parameter
        // passed as `{ type: "reference" }` makes the action throw
        // ERROR_ACTION_RUNTIME_ERROR at run time — the docs say a
        // single-expression reference is "type-preserving and passes the whole
        // object", and for this parameter it is not. Pinned and unmapped, the
        // same headers arrive intact. Measured both ways; see clay/WORKFLOW.md.
        // Retry the transient classes only: 429 and 5xx. A 400 means the
        // request is wrong (a bad schema, an unsupported parameter) and no
        // number of retries will fix it — it must surface.
        //
        // As a `map`, NOT as `retryOptions|maxRetries` pipe keys. Pipe keys are
        // the documented way to address a grouped parameter, and Clay accepts
        // them at save time — then the action throws
        // ERROR_ACTION_RUNTIME_ERROR at run time. `retryOptions` is declared as
        // one parameter and takes one object value.
        shouldRetry: fixed(true),
        retryOptions: {
          type: 'map',
          entries: {
            maxRetries: fixed(3),
            statusCodesToRetry: fixed(['429', '500-599']),
          },
        },
        // 90s. The ceiling is 100000ms, stated in the parameter's own
        // description in `clay workflows actions schema`.
        responseTimeout: fixed(90000),
      }),
      incomingEdges: [{ __from: after }],
    },
  };
}

// ---------------------------------------------------------------------------
// The graph
// ---------------------------------------------------------------------------

const CLASSIFIER_CALLS = COMPONENTS.map(([component, title], i) => openAiNode({
  name: `${17 + i} Classify ${title}`,
  bodyFrom: '16 Build classifier requests',
  bodyPath: `$.body_${component}`,
  // Chained, not fanned out. Each is still its own node and its own HTTP call,
  // so one bad component fails and retries alone — but chaining guarantees node
  // 24 is activated exactly once, and therefore that exactly one `icp.scored`
  // event is POSTed per request. A seven-way fan-in would have made that depend
  // on undocumented join semantics.
  after: i === 0 ? '16 Build classifier requests' : `${16 + i} Classify ${COMPONENTS[i - 1][1]}`,
}));
const LAST_CLASSIFIER = CLASSIFIER_CALLS[CLASSIFIER_CALLS.length - 1].name;

export const NODES = [
  {
    name: '01 Prepare enrichment inputs',
    spec: {
      nodeType: 'code',
      name: '01 Prepare enrichment inputs',
      code: read('clay/code/01_prepare.py'),
      inputSchema: properties(
        Object.fromEntries(WEBHOOK_KEYS.map((k) => [k, pin(TRIGGER, `$.${k}`)])),
      ),
      incomingEdges: [{ __from: TRIGGER }],
    },
  },

  {
    name: '02 Gate — any identifier to enrich?',
    spec: {
      nodeType: 'conditional',
      name: '02 Gate — any identifier to enrich?',
      conditionalMode: 'rules',
      inputSchema: properties({
        enrichable: pin('01 Prepare enrichment inputs', '$.enrichable', 'boolean'),
      }),
      rulesConditionalConfig: {
        rules: [{
          id: 'enrichable',
          name: 'Domain or LinkedIn URL present',
          condition: {
            type: 'GroupOp',
            combinationMode: 'And',
            items: [{ type: 'BinOp', dataPath: ['enrichable'], operator: 'True' }],
          },
        }],
      },
      incomingEdges: [{ __from: '01 Prepare enrichment inputs' }],
    },
  },

  {
    name: '03 Enrich company profile',
    spec: {
      nodeType: 'tool',
      name: '03 Enrich company profile',
      ...resilient(...FROM_IDENTIFIER),
      tools: tool(PKG.cpj, 'cpj-enrich-company', {
        company_identifier: item(),
      }),
      incomingEdges: [{ __from: '02 Gate — any identifier to enrich?', ruleId: 'enrichable' }],
    },
  },

  {
    name: '04 Resolve domain for enrichment',
    spec: {
      nodeType: 'code',
      name: '04 Resolve domain for enrichment',
      code: read('clay/code/04_resolve_domain.py'),
      inputSchema: properties({
        domain: pin('01 Prepare enrichment inputs', '$.domain'),
        profile_domain: pin('03 Enrich company profile', '$.results[0].domain'),
        profile_website: pin('03 Enrich company profile', '$.results[0].website'),
      }),
      incomingEdges: [{ __from: '03 Enrich company profile' }],
    },
  },

  {
    name: '05 Gate — domain resolved?',
    spec: {
      nodeType: 'conditional',
      name: '05 Gate — domain resolved?',
      conditionalMode: 'rules',
      inputSchema: properties({
        has_domain: pin('04 Resolve domain for enrichment', '$.has_domain', 'boolean'),
      }),
      rulesConditionalConfig: {
        rules: [{
          id: 'has_domain',
          name: 'Domain available',
          condition: {
            type: 'GroupOp',
            combinationMode: 'And',
            items: [{ type: 'BinOp', dataPath: ['has_domain'], operator: 'True' }],
          },
        }],
      },
      incomingEdges: [{ __from: '04 Resolve domain for enrichment' }],
    },
  },

  {
    name: '06 Scrape site pages',
    spec: {
      nodeType: 'tool',
      name: '06 Scrape site pages',
      // Runs once per URL over the four pages clay_table_spec.md section 5
      // names. ignore_errors because a company without a /product page is a
      // fact about the company, not a failure of the run.
      listMode: true,
      listFailureMode: 'ignore_errors',
      listEntriesRef: { __fromRef: '04 Resolve domain for enrichment', path: '$.page_urls' },
      tools: tool(PKG.clay, 'scrape-website', {
        url: item(),
        outputFields: fixed(['title', 'description', 'bodyText']),
        enableJavaScriptRendering: fixed(true),
      }),
      incomingEdges: [{ __from: '05 Gate — domain resolved?', ruleId: 'has_domain' }],
    },
  },

  {
    name: '07 Collect page text',
    spec: {
      nodeType: 'code',
      name: '07 Collect page text',
      code: read('clay/code/07_collect_pages.py'),
      inputSchema: properties({
        pages: pin('06 Scrape site pages', '$.results', 'array'),
      }),
      incomingEdges: [{ __from: '06 Scrape site pages' }],
    },
  },

  {
    name: '08 Build website summary request',
    spec: {
      nodeType: 'code',
      name: '08 Build website summary request',
      code: read('clay/code/08_build_summary_request.py').replace('@@SUMMARY_MODEL@@', MODELS.summary),
      inputSchema: properties({
        page_text: pin('07 Collect page text', '$.page_text'),
        pages_reachable: pin('07 Collect page text', '$.pages_reachable'),
        company_name: pin('01 Prepare enrichment inputs', '$.company_name'),
        openai_api_key: pin('01 Prepare enrichment inputs', '$.openai_api_key'),
      }),
      incomingEdges: [{ __from: '07 Collect page text' }],
    },
  },

  openAiNode({
    name: '09 Summarize website',
    bodyFrom: '08 Build website summary request',
    bodyPath: '$.summary_request',
    after: '08 Build website summary request',
  }),

  {
    name: '10 Read website summary',
    spec: {
      nodeType: 'code',
      name: '10 Read website summary',
      code: read('clay/code/10_read_summary.py'),
      inputSchema: properties({
        response: pin('09 Summarize website', '$.result', 'object'),
      }),
      incomingEdges: [{ __from: '09 Summarize website' }],
    },
  },

  {
    name: '11 Enrich revenue and headcount',
    spec: {
      nodeType: 'tool',
      name: '11 Enrich revenue and headcount',
      ...resilient(...FROM_DOMAIN),
      // NEEDS_DECISION #9's default named Apollo as primary for revenue. This
      // workspace's Apollo connection returns "Invalid access credentials", and
      // People Data Labs covers the same ground and more: inferred revenue,
      // total headcount, and `employee_count_by_role.engineering`, which is
      // `eng_headcount_estimate` directly rather than by inference.
      tools: tool(PKG.pdl, 'pdl-enrich-company-v3', {
        website: item(),
      }),
      incomingEdges: [{ __from: '10 Read website summary' }],
    },
  },

  {
    name: '12 Find financing events',
    spec: {
      nodeType: 'tool',
      name: '12 Find financing events',
      ...resilient(...FROM_DOMAIN),
      tools: tool(PKG.predictleads, 'predict-leads-get-financing-events-for-company-v3', {
        unparsedDomain: item(),
      }),
      incomingEdges: [{ __from: '11 Enrich revenue and headcount' }],
    },
  },

  {
    name: '13 Find open engineering roles',
    spec: {
      nodeType: 'tool',
      name: '13 Find open engineering roles',
      ...resilient(...FROM_DOMAIN),
      tools: tool(PKG.predictleads, 'predict-leads-get-job-openings-for-company-v3', {
        unparsedDomain: item(),
      }),
      incomingEdges: [{ __from: '12 Find financing events' }],
    },
  },

  {
    name: '14 Find recent news',
    spec: {
      nodeType: 'tool',
      name: '14 Find recent news',
      ...resilient(...FROM_DOMAIN),
      tools: tool(PKG.predictleads, 'predict-leads-get-events-for-company-v3', {
        unparsedDomain: item(),
        found_at_from: fixed('365 days ago'),
      }),
      incomingEdges: [{ __from: '13 Find open engineering roles' }],
    },
  },

  {
    name: '15 Build facts_json',
    spec: {
      nodeType: 'code',
      name: '15 Build facts_json',
      code: read('clay/code/15_build_facts.py'),
      inputSchema: properties({
        request_id: pin('01 Prepare enrichment inputs', '$.request_id'),
        org_id: pin('01 Prepare enrichment inputs', '$.org_id'),
        deal_id: pin('01 Prepare enrichment inputs', '$.deal_id'),
        identifier_kind: pin('01 Prepare enrichment inputs', '$.identifier_kind'),
        identifier_value: pin('01 Prepare enrichment inputs', '$.identifier_value'),
        domain: pin('01 Prepare enrichment inputs', '$.domain'),
        linkedin_url: pin('01 Prepare enrichment inputs', '$.linkedin_url'),
        company_name: pin('01 Prepare enrichment inputs', '$.company_name'),
        hq_country: pin('01 Prepare enrichment inputs', '$.hq_country'),
        hq_state: pin('01 Prepare enrichment inputs', '$.hq_state'),

        domain_for_enrichment: pin('04 Resolve domain for enrichment', '$.domain_for_enrichment'),

        profile_employee_count: pin('03 Enrich company profile', '$.results[0].employee_count', 'number'),
        profile_industry: pin('03 Enrich company profile', '$.results[0].industry'),
        profile_description: pin('03 Enrich company profile', '$.results[0].description'),
        profile_founded: pin('03 Enrich company profile', '$.results[0].founded', 'number'),
        profile_locality: pin('03 Enrich company profile', '$.results[0].locality'),
        profile_country: pin('03 Enrich company profile', '$.results[0].country'),
        profile_annual_revenue: pin('03 Enrich company profile', '$.results[0].annual_revenue'),

        website_summary: pin('10 Read website summary', '$.website_summary'),
        // Reconciles the jobs provider against the company's own careers page.
        careers_lists_openings: pin('10 Read website summary', '$.careers_lists_openings'),
        website_pages_reachable: pin('07 Collect page text', '$.pages_reachable'),

        pdl_revenue: pin('11 Enrich revenue and headcount', '$.results[0].inferred_revenue'),
        pdl_employee_count: pin('11 Enrich revenue and headcount', '$.results[0].employee_count', 'number'),
        pdl_eng_headcount: pin('11 Enrich revenue and headcount', '$.results[0].employee_count_by_role.engineering', 'number'),
        pdl_funding_stage: pin('11 Enrich revenue and headcount', '$.results[0].latest_funding_stage'),
        pdl_last_funding_date: pin('11 Enrich revenue and headcount', '$.results[0].last_funding_date'),
        pdl_summary: pin('11 Enrich revenue and headcount', '$.results[0].summary'),

        financing_events: pin('12 Find financing events', '$.results[0].events', 'array'),
        jobs: pin('13 Find open engineering roles', '$.results[0].jobs', 'array'),
        jobs_domain: pin('13 Find open engineering roles', '$.results[0].domain'),
        news_events: pin('14 Find recent news', '$.results[0].events', 'array'),
        news_domain: pin('14 Find recent news', '$.results[0].domain'),
      }),
      // Three ways in: the full waterfall, or either gate's no-match route.
      // Exactly one fires, because a conditional picks exactly one edge — so
      // this node runs once however the request arrived.
      incomingEdges: [
        { __from: '14 Find recent news' },
        { __from: '02 Gate — any identifier to enrich?', isDefaultRoute: true },
        { __from: '05 Gate — domain resolved?', isDefaultRoute: true },
      ],
    },
  },

  {
    name: '16 Build classifier requests',
    spec: {
      nodeType: 'code',
      name: '16 Build classifier requests',
      code: classifierRequestCode(),
      codeTimeoutMs: 30000,
      inputSchema: properties({
        facts_json: pin('15 Build facts_json', '$.facts_json'),
        openai_api_key: pin('01 Prepare enrichment inputs', '$.openai_api_key'),
      }),
      incomingEdges: [{ __from: '15 Build facts_json' }],
    },
  },

  ...CLASSIFIER_CALLS,

  {
    name: '24 Collect classifier outputs',
    spec: {
      nodeType: 'code',
      name: '24 Collect classifier outputs',
      code: read('clay/code/24_collect_classifiers.py'),
      inputSchema: properties({
        ...Object.fromEntries(
          COMPONENTS.map(([component, title], i) => [
            `reply_${component}`,
            pin(`${17 + i} Classify ${title}`, '$.result', 'object'),
          ]),
        ),
        // Set by node 15 when the two revenue providers landed two or more
        // bands apart. Node 24 forces revenue_range to low confidence on it.
        revenue_conflict: pin('15 Build facts_json', '$.revenue_conflict', 'boolean'),
      }),
      incomingEdges: [{ __from: LAST_CLASSIFIER }],
    },
  },

  {
    name: '25 Score (ICP v5)',
    spec: {
      nodeType: 'code',
      name: '25 Score (ICP v5)',
      code: SCORER + read('clay/code/25_score_handler.py'),
      codeTimeoutMs: 30000,
      inputSchema: properties({
        components: pin('24 Collect classifier outputs', '$.components', 'object'),
        revenue_usd: pin('15 Build facts_json', '$.revenue_usd', 'number'),
        headcount_total: pin('15 Build facts_json', '$.headcount_total', 'number'),
        headcount_eng: pin('15 Build facts_json', '$.headcount_eng', 'number'),
      }),
      incomingEdges: [{ __from: '24 Collect classifier outputs' }],
    },
  },

  {
    name: '26 Build icp.scored event',
    spec: {
      nodeType: 'code',
      name: '26 Build icp.scored event',
      code: read('clay/code/26_build_event.py'),
      inputSchema: properties({
        request_id: pin('01 Prepare enrichment inputs', '$.request_id'),
        org_id: pin('01 Prepare enrichment inputs', '$.org_id'),
        deal_id: pin('01 Prepare enrichment inputs', '$.deal_id'),
        identifier_kind: pin('01 Prepare enrichment inputs', '$.identifier_kind'),
        identifier_value: pin('01 Prepare enrichment inputs', '$.identifier_value'),
        callback_url: pin('01 Prepare enrichment inputs', '$.callback_url'),
        score: pin('25 Score (ICP v5)', '$.score', 'object'),
        components: pin('25 Score (ICP v5)', '$.components', 'object'),
        facts_summary: pin('25 Score (ICP v5)', '$.facts_summary', 'object'),
      }),
      incomingEdges: [{ __from: '25 Score (ICP v5)' }],
    },
  },

  {
    name: '27 POST icp.scored to n8n Path B',
    spec: {
      nodeType: 'tool',
      name: '27 POST icp.scored to n8n Path B',
      inputSchema: properties({
        url: pin('26 Build icp.scored event', '$.callback_url'),
        body: pin('26 Build icp.scored event', '$.event_json'),
        headers: pin('26 Build icp.scored event', '$.headers', 'object'),
      }),
      tools: tool(PKG.clay, 'http-api-v2', {
        method: fixed('POST'),
        // Never hardcoded: the callback URL is what n8n sent with the request,
        // so DEV and production differ by payload, not by node config.
        url: ref('{{url}}'),
        body: ref('{{body}}'),
        // Same as the OpenAI nodes: `headers` comes from the pin, never from a
        // reference mapping. See clay/WORKFLOW.md.
        // 3x on 5xx, never on 4xx (clay_table_spec.md section 9). A 4xx is n8n
        // rejecting the event as malformed or unauthorized; retrying cannot fix
        // either and must surface as a failed run.
        shouldRetry: fixed(true),
        retryOptions: {
          type: 'map',
          entries: {
            maxRetries: fixed(3),
            statusCodesToRetry: fixed(['500-599']),
          },
        },
      }),
      incomingEdges: [{ __from: '26 Build icp.scored event' }],
    },
  },
];

// ---------------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------------

function resolvePins(value, ids) {
  if (Array.isArray(value)) return value.map((v) => resolvePins(v, ids));
  if (value && typeof value === 'object') {
    if (value.__from !== undefined) {
      const { __from, ...rest } = value;
      const sourceNodeId = ids[__from];
      if (!sourceNodeId) throw new Error(`unresolved node reference: ${__from}`);
      return rest.sourcePath !== undefined
        ? { ...rest, sourceNodeId }
        : { ...rest, sourceNode: sourceNodeId };
    }
    if (value.__fromRef !== undefined) {
      const { __fromRef, ...rest } = value;
      const sourceNodeId = ids[__fromRef];
      if (!sourceNodeId) throw new Error(`unresolved node reference: ${__fromRef}`);
      return { ...rest, sourceNodeId };
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, resolvePins(v, ids)]));
  }
  return value;
}

function main() {
  const graph = clay(['workflows', 'graph', 'get', WORKFLOW_ID, '--mode', 'summary']);
  const existing = new Map((graph.summary?.nodes ?? []).map((n) => [n.name, n.id]));
  const triggers = graph.summary?.triggers ?? [];

  // --- the Path A trigger ---------------------------------------------------
  // Created but NEVER published by this script. Publishing is what takes a
  // trigger live, and taking Path A live is the user's decision.
  // The graph summary lists a trigger's id and type but not its canvas node id,
  // so the node id is read back from `triggers get`. Skipping that read is how
  // a second trigger gets created on a re-run — a trigger may have only one
  // outgoing edge, so the first is then orphaned and `graph validate` fails
  // with trigger_not_connected.
  let triggerNodeId = triggers.length
    ? clay(['workflows', 'triggers', 'get', triggers[0].id]).workflowNodeId
    : null;
  if (!triggerNodeId) {
    const created = clay(['workflows', 'triggers', 'create', WORKFLOW_ID], {
      triggerType: 'webhook',
      inputSchema: properties(Object.fromEntries(
        WEBHOOK_KEYS.map((k) => [k, { type: k === 'deal_id' ? 'string' : 'string' }]),
      )),
    });
    const trigger = clay(['workflows', 'triggers', 'get', created.resourceId]);
    triggerNodeId = trigger.workflowNodeId;
    console.log(`trigger      created  ${created.resourceId} -> node ${triggerNodeId}`);
  } else {
    console.log(`trigger      reused   node ${triggerNodeId}`);
  }

  // --- pass 0: sweep away nodes this builder used to create but no longer does
  //
  // Every node this script creates is named "NN Something". Renumbering or
  // dropping a step would otherwise leave the old node stranded on the canvas,
  // still wired, still running. The sweep is scoped to that naming convention
  // so it can never touch a node a human added by hand.
  const wanted = new Set(NODES.map((n) => n.name));
  for (const [name, id] of existing) {
    if (/^\d{2} /.test(name) && !wanted.has(name)) {
      clay(['workflows', 'nodes', 'delete', WORKFLOW_ID, id]);
      existing.delete(name);
      console.log(`${name.padEnd(36)} removed  ${id}`);
    }
  }

  // --- pass 1: make sure every node exists, so its id can be referenced ----
  // Nodes are created as stubs (type and name only). nodeType is fixed at
  // create and cannot be changed later, so it has to be right here; everything
  // else lands in pass 2.
  const ids = { [TRIGGER]: triggerNodeId };
  for (const node of NODES) {
    const id = existing.get(node.name);
    if (id) {
      ids[node.name] = id;
      continue;
    }
    const result = clay(['workflows', 'nodes', 'create', WORKFLOW_ID], {
      nodeType: node.spec.nodeType,
      name: node.spec.name,
    });
    ids[node.name] = result.nodeId;
    console.log(`${node.name.padEnd(36)} created  ${result.nodeId}`);
    reportFailures(node.name, result);
  }

  // --- pass 2: one full update per node, body and wiring together ----------
  //
  // Body and wiring go in the SAME call deliberately. Updating `inputSchema`
  // on a code node in a call that does not also carry `code` reverts that
  // node's `code` to its previous value — silently, with
  // `appliedUpdates: [{field: "inputSchema", success: true}]`. Measured on this
  // workspace, 2026-09-15; see REPORT.md. Sending both together is the
  // workaround, and pass 3 below is what proves it held.
  for (const node of NODES) {
    const { nodeType, ...body } = node.spec;   // nodeType is create-only
    const payload = resolvePins(body, ids);
    const result = clay(['workflows', 'nodes', 'update', WORKFLOW_ID, ids[node.name]], payload);
    console.log(`${node.name.padEnd(36)} configured`);
    reportFailures(node.name, result);
  }

  // --- pass 3: read every node back and diff what actually landed ---------
  // `nodes update` reports success per field, but the only proof that a Python
  // handler or a prompt persisted byte for byte is reading it back. A silently
  // stale code node is the worst failure mode here: the graph validates, the
  // run succeeds, and the numbers come from last week's rubric.
  let drift = 0;
  for (const node of NODES) {
    const live = clay(['workflows', 'nodes', 'get', WORKFLOW_ID, ids[node.name]]).node ?? {};
    for (const field of ['code', 'agentPrompt', 'agentModel']) {
      const want = node.spec[field];
      if (want === undefined) continue;
      if (live[field] !== want) {
        drift += 1;
        console.error(`  !! ${node.name}: ${field} did not persist (live ${
          typeof live[field] === 'string' ? `${live[field].length} chars` : String(live[field])
        }, wanted ${typeof want === 'string' ? `${want.length} chars` : String(want)})`);
      }
    }
  }
  console.log(drift === 0
    ? 'verified: every code node and prompt on the canvas matches this repository.'
    : `VERIFY FAILED: ${drift} field(s) did not persist.`);

  console.log(`\n${NODES.length} nodes, ${calls} CLI calls. Not published — the Path A trigger stays inert.`);
  if (drift > 0) process.exit(1);
}

function reportFailures(name, result) {
  for (const update of result?.appliedUpdates ?? []) {
    if (update.success === false) {
      console.error(`  !! ${name}: ${update.field} — ${update.message ?? 'rejected'}`);
    }
  }
}

// Importable without side effects: tests/static/clay_nodes.test.mjs imports the
// generators to check what they emit, and must not touch the workspace.
const isMain = process.argv[1] && process.argv[1].endsWith('build_workflow.mjs');
if (isMain) main();
