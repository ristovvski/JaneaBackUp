// tests/contract/prompts.test.mjs — no rubric text is hardcoded in a prompt.
//
// The point of §9.2 is that changing a level definition is one edit to
// config/rubric_v5.json. That only holds if every prompt carries the rubric
// text byte for byte and the generator has been re-run. Both are asserted
// here, by reading the config — never by string literals in this file.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PROMPTS = join(ROOT, 'engine', 'prompts');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v5.json'), 'utf8'));

const readPrompt = (name) => readFileSync(join(PROMPTS, `${name}.md`), 'utf8');

const LEVEL_COMPONENTS = ['stage_maturity', 'company_type', 'geography', 'revenue_range', 'buying_signal'];
const ALL_COMPONENTS = [...LEVEL_COMPONENTS, 'industry_vertical', 'activation_state'];

/** Extract the ```allowed-values fenced block a prompt declares. */
function allowedValues(text) {
  const match = text.match(/```allowed-values\n([\s\S]*?)\n```/);
  if (!match) return null;
  return match[1].split('\n').map((l) => l.trim()).filter((l) => l !== '');
}

describe('the prompt files exist and are current', () => {
  test('one prompt per classifier plus the shared preamble', () => {
    assert.deepEqual(
      readdirSync(PROMPTS).filter((f) => f.endsWith('.md')).sort(),
      ['_preamble.md', ...ALL_COMPONENTS.map((c) => `${c}.md`)].sort()
    );
  });

  test('re-running the generator reproduces every prompt byte for byte', () => {
    const names = [...ALL_COMPONENTS, '_preamble'];
    const before = Object.fromEntries(names.map((c) => [c, readPrompt(c)]));
    execFileSync(process.execPath, [join(ROOT, 'scripts', 'gen_prompts.mjs')], { stdio: 'pipe' });
    for (const name of names) {
      assert.equal(
        readPrompt(name), before[name],
        `engine/prompts/${name}.md is stale — run \`npm run gen:prompts\` and commit`
      );
    }
  });
});

describe('every level definition is the rubric text, byte for byte', () => {
  for (const component of LEVEL_COMPONENTS) {
    test(`${component}.md embeds all four component_scales strings`, () => {
      const text = readPrompt(component);
      const scale = RUBRIC.component_scales[component];
      for (const [level, definition] of Object.entries(scale)) {
        assert.ok(
          text.includes(definition),
          `${component}.md is missing the level ${level} definition from config:\n  ${definition}`
        );
      }
    });

    test(`${component}.md presents the levels in descending order`, () => {
      const text = readPrompt(component);
      const positions = ['10', '7', '3', '0'].map(
        (level) => text.indexOf(RUBRIC.component_scales[component][level])
      );
      for (let i = 1; i < positions.length; i += 1) {
        assert.ok(positions[i] > positions[i - 1], `${component}: level order is scrambled`);
      }
    });
  }

  test('activation_state.md embeds all four state definitions', () => {
    const text = readPrompt('activation_state');
    for (const [state, definition] of Object.entries(RUBRIC.component_scales.activation_state)) {
      assert.ok(text.includes(definition), `activation_state.md is missing the ${state} definition`);
    }
  });

  test('a prompt does not carry another component\'s level text', () => {
    for (const component of LEVEL_COMPONENTS) {
      const text = readPrompt(component);
      for (const other of LEVEL_COMPONENTS) {
        if (other === component) continue;
        for (const definition of Object.values(RUBRIC.component_scales[other])) {
          if (Object.values(RUBRIC.component_scales[component]).includes(definition)) continue;
          assert.ok(
            !text.includes(definition),
            `${component}.md leaks a ${other} level definition:\n  ${definition}`
          );
        }
      }
    }
  });
});

describe('industry_vertical.md lists the 17 verticals and nothing else', () => {
  const text = readPrompt('industry_vertical');
  const declared = allowedValues(text);

  test('the allowed-values block exists', () => {
    assert.ok(declared !== null, 'no ```allowed-values block found');
  });

  test('it contains all 17 vertical strings from config', () => {
    const expected = Object.keys(RUBRIC.industry_verticals);
    assert.equal(expected.length, 17);
    for (const vertical of expected) {
      assert.ok(declared.includes(vertical), `the allowed list is missing "${vertical}"`);
    }
  });

  test('it contains NO other value', () => {
    const expected = new Set(Object.keys(RUBRIC.industry_verticals));
    for (const value of declared) {
      assert.ok(expected.has(value), `the allowed list contains "${value}", which is not a rubric vertical`);
    }
    assert.equal(declared.length, 17, 'exactly 17 entries, no duplicates');
  });

  test('the order matches config, so a diff of either file is readable', () => {
    assert.deepEqual(declared, Object.keys(RUBRIC.industry_verticals));
  });

  test('every vertical also appears with its tier, from config', () => {
    for (const [vertical, row] of Object.entries(RUBRIC.industry_verticals)) {
      assert.ok(text.includes(vertical), vertical);
      assert.ok(
        text.includes(`| ${vertical} | ${row.tier} | ${row.total} |`),
        `${vertical} row must carry tier ${row.tier} and total ${row.total} from config`
      );
    }
  });

  test('it forbids any other string in so many words', () => {
    assert.match(text, /Any other string is a\s*\nschema violation/);
  });
});

describe('activation_state.md declares the four states and the multipliers', () => {
  const text = readPrompt('activation_state');
  const declared = allowedValues(text);

  test('the allowed-values block is exactly the four rubric states, in config order', () => {
    assert.deepEqual(declared, Object.keys(RUBRIC.component_scales.activation_state));
  });

  test('each multiplier is printed from config', () => {
    for (const [state, m] of Object.entries(RUBRIC.activation_multipliers)) {
      assert.ok(
        text.includes(`| \`${state}\` | ×${m.toFixed(2)} |`),
        `the multiplier row for ${state} (×${m.toFixed(2)}) is missing`
      );
    }
  });

  test('the Contracting evidence window is printed from config, not as a literal', () => {
    const months = RUBRIC.activation_contracting_evidence_max_age_months;
    assert.ok(text.includes(`${months}\n   months`) || text.includes(`${months} months`), 'window');
    assert.ok(text.includes(`\`${RUBRIC.activation_default_when_no_evidence}\``), 'the fallback state');
  });
});

describe('every prompt declares its own component and weight from config', () => {
  for (const component of ALL_COMPONENTS) {
    test(`${component}.md`, () => {
      const text = readPrompt(component);
      const weightKey = component === 'industry_vertical' ? 'industries' : component;
      const weight = RUBRIC.weights[weightKey];

      assert.ok(text.includes(`**Component:** \`${component}\``), 'component name');
      assert.ok(text.includes(`"component": "${component}"`), 'the output contract names it too');
      assert.ok(text.includes(`**Model version:** ${RUBRIC.model_version}`), 'model version');

      if (component === 'activation_state') {
        // A multiplier, not a weighted component: it must NOT claim a weight.
        assert.equal(RUBRIC.weights[weightKey], undefined);
        assert.ok(text.includes('**Applies as:** multiplier on the composite'), 'multiplier role');
        assert.ok(!/\*\*Weight:\*\*/.test(text), 'must not claim a weight');
      } else {
        assert.equal(typeof weight, 'number', `${component} must have a weight in config`);
        assert.ok(text.includes(`**Weight:** ${weight} of 100`), `weight ${weight}`);
      }
    });
  }

  test('buying_signal says out loud that its weight is 0', () => {
    const text = readPrompt('buying_signal');
    assert.equal(RUBRIC.weights.buying_signal, 0);
    assert.ok(text.includes(`The weight of this component is \`${RUBRIC.weights.buying_signal}\``));
    assert.match(text, /cannot\*\* move the\s*\ncomposite/);
  });
});

describe('the shared preamble carries the §7 rules', () => {
  const text = readPrompt('_preamble');

  test('facts-only, no browsing, no assuming', () => {
    assert.match(text, /Never browse\. Never assume\./);
  });

  test('insufficient facts -> confidence low + missing_inputs', () => {
    assert.match(text, /set `confidence` to `"low"`/);
    assert.match(text, /list the fact keys you needed in `missing_inputs`/);
  });

  test('JSON only, matching the schema', () => {
    assert.match(text, /One JSON object\./);
    assert.match(text, /classifier_output\.schema\.json/);
  });

  test('evidence is cited as <fact_key>: <value>', () => {
    assert.match(text, /Cite every evidence item as `<fact_key>: <value>`/);
  });

  test('the Contracting rule names the config window and the fallback state', () => {
    const months = RUBRIC.activation_contracting_evidence_max_age_months;
    assert.ok(text.includes(`**${months}** months`), `the ${months}-month window`);
    assert.ok(
      text.includes(`return \`${RUBRIC.activation_default_when_no_evidence}\``),
      'the fallback state'
    );
  });

  test('it names the three components that gate insufficient_data, from config', () => {
    for (const component of RUBRIC.insufficient_data_rule.components) {
      assert.ok(text.includes(`\`${component}\``), `${component} must be named in the preamble`);
    }
  });

  test('it does not restate any level definition — that is the components\' job', () => {
    for (const component of LEVEL_COMPONENTS) {
      for (const definition of Object.values(RUBRIC.component_scales[component])) {
        assert.ok(!text.includes(definition), `_preamble.md leaks a ${component} level definition`);
      }
    }
  });
});

describe('no prompt hardcodes a number the rubric owns', () => {
  test('no prompt states a weight, threshold or multiplier that config disagrees with', () => {
    // Any "N of 100" claim in a prompt must match that component's real weight.
    for (const component of ALL_COMPONENTS) {
      if (component === 'activation_state') continue; // a multiplier, no weight
      const text = readPrompt(component);
      const weightKey = component === 'industry_vertical' ? 'industries' : component;
      const real = RUBRIC.weights[weightKey];
      for (const match of text.matchAll(/(\d+) of 100/g)) {
        assert.equal(
          Number(match[1]), real,
          `${component}.md claims a weight of ${match[1]} but config says ${real}`
        );
      }
    }
  });

  test('no prompt names a grade threshold — grading is not a classifier concern', () => {
    for (const component of ALL_COMPONENTS) {
      const text = readPrompt(component);
      assert.ok(!/\bICP [ABC]\b/.test(text), `${component}.md mentions a grade label`);
      assert.ok(
        !text.includes(`>= ${RUBRIC.thresholds.A}`) && !text.includes(`≥ ${RUBRIC.thresholds.A}`),
        `${component}.md mentions the A threshold`
      );
    }
  });
});
