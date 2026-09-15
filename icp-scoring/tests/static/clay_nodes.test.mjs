// tests/static/clay_nodes.test.mjs — the Python that runs inside Clay, checked offline.
//
// A Clay code node fails at run time, in a workspace, after credits have been
// spent on the enrichment upstream of it. Everything checkable before that
// point is checked here:
//
//   - every handler parses, and defines handler(context);
//   - only modules the Clay code-node runtime actually allows are imported
//     (it is a short allow-list, and `datetime` is NOT on it — that one cost a
//     full run to discover);
//   - the scoring node embeds engine/clay_score.py byte-for-byte, so the
//     parity-tested scorer is what runs;
//   - the generated classifier node carries the real prompts and the real
//     strict schemas, not a placeholder;
//   - no credential-shaped literal is in any of it.
//
// Skips loudly if python3 is absent. A skip is never a pass.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  classifierRequestCode, classifierPrompt, COMPONENTS, STRICT_SCHEMAS, MODELS, NODES,
} from '../../clay/build_workflow.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const readText = (...p) => readFileSync(join(ROOT, ...p), 'utf8');

const CODE_DIR = join(ROOT, 'clay', 'code');
const files = readdirSync(CODE_DIR).filter((f) => f.endsWith('.py')).sort();

// Measured against the live node runtime on 2026-09-15 by running a probe node
// that __import__s each name. This is NOT the module set `clay workflows code
// test` offers — that sandbox is more permissive, which is exactly why a
// code-test pass does not mean a node will run.
const ALLOWED_MODULES = new Set([
  'json', 'time', 'math', 're', 'os', 'sys', 'collections',
  'itertools', 'functools', 'random', 'operator', 'copy', 'textwrap', 'typing',
]);

// Printed by python3: the top-level module names a source file imports.
const IMPORTS_SCRIPT = `
import ast, json, sys
tree = ast.parse(sys.stdin.read())
names = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        if node.module and node.level == 0:
            names.add(node.module.split(".")[0])
print(json.dumps(sorted(names)))
`;

let python3 = null;
try {
  execFileSync('python3', ['--version'], { stdio: 'pipe' });
  python3 = 'python3';
} catch { /* reported below */ }

describe('Clay code nodes', () => {
  test('python3 is available to check the handlers', () => {
    assert.ok(
      python3,
      'python3 not found — the Clay handlers were NOT syntax-checked. This is a skip, not a pass.',
    );
  });

  test('the file set matches the graph', () => {
    assert.deepEqual(files, [
      '01_prepare.py',
      '04_resolve_domain.py',
      '07_collect_pages.py',
      '08_build_summary_request.py',
      '10_read_summary.py',
      '15_build_facts.py',
      '16_build_classifier_requests.py',
      '24_collect_classifiers.py',
      '25_score_handler.py',
      '26_build_event.py',
    ]);
  });

  for (const file of files) {
    const source = readText('clay', 'code', file);

    test(`${file}: imports only what the Clay runtime allows`, { skip: !python3 }, () => {
      // Via the AST, not a regex. These files embed prompt text, and prose like
      // "a fact not on these pages is not evidence, and using it makes" sits on
      // a line starting with "from elsewhere" inside a triple-quoted string —
      // which a line-based regex reads as an import of a module named
      // `elsewhere`. The parser knows the difference.
      const imported = JSON.parse(execFileSync(python3, ['-c', IMPORTS_SCRIPT], {
        input: source.replace(/@@[A-Z_]+@@/g, 'placeholder'),
        encoding: 'utf8',
      }));
      for (const name of imported) {
        assert.ok(
          ALLOWED_MODULES.has(name),
          `${file} imports "${name}", which the Clay code-node runtime rejects with `
          + 'ModuleNotFoundError. Allowed: ' + [...ALLOWED_MODULES].join(', '),
        );
      }
    });

    test(`${file}: parses, and defines handler(context)`, { skip: !python3 }, () => {
      // 25_score_handler.py is a fragment: it is appended to
      // engine/clay_score.py and only makes sense with it.
      const body = file === '25_score_handler.py'
        ? readText('engine', 'clay_score.py') + source
        : source;
      const checked = body.replace(/@@[A-Z_]+@@/g, 'placeholder');
      execFileSync(python3, ['-c', 'import ast,sys; ast.parse(sys.stdin.read())'], {
        input: checked, stdio: ['pipe', 'pipe', 'pipe'],
      });
      if (file !== '25_score_handler.py' || true) {
        assert.match(body, /^def handler\(context\):/m, `${file} has no handler(context)`);
      }
    });

    test(`${file}: carries no credential-shaped literal`, () => {
      // The OpenAI key reaches Clay through the request payload and is
      // referenced by name; it is never a literal anywhere in this repository.
      assert.doesNotMatch(source, /\bsk-[A-Za-z0-9_-]{20,}/, `${file} contains an API key`);
      assert.doesNotMatch(source, /\bBearer\s+[A-Za-z0-9._-]{20,}/, `${file} contains a bearer token`);
    });
  }

  test('25_score_handler.py does not redefine anything in the scorer', () => {
    const scorer = readText('engine', 'clay_score.py');
    const handler = readText('clay', 'code', '25_score_handler.py');
    const defsIn = (src) => new Set([...src.matchAll(/^def\s+(\w+)/gm)].map((m) => m[1]));
    const collisions = [...defsIn(handler)].filter((name) => defsIn(scorer).has(name));
    assert.deepEqual(
      collisions, [],
      `the handler redefines ${collisions.join(', ')} from engine/clay_score.py — `
      + 'the scorer would be silently overridden',
    );
  });

  test('16_build_classifier_requests.py still has its generation markers', () => {
    // The file in the repo is a TEMPLATE. clay/build_workflow.mjs substitutes
    // the prompts, the schemas and the model id at build time. If a marker went
    // missing the build would ship a node with no prompts and no schema, and
    // the API would answer with whatever it liked.
    const source = readText('clay', 'code', '16_build_classifier_requests.py');
    assert.match(source, /@@CLASSIFIER_MODEL@@/);
    assert.match(source, /# @@GENERATED@@/);
  });

  // -------------------------------------------------------------------------
  // What the generated classifier node ACTUALLY contains.
  //
  // This block exists because two real bugs got past everything else. The
  // builder embedded each strict schema as a JSON *string* rather than an
  // object (read() returns text, and nothing parsed it), which OpenAI answered
  // with ERROR_ACTION_RUNTIME_ERROR after the enrichment above it had already
  // been paid for. And the JSON-to-Python conversion was textual, so it rewrote
  // the word "null" inside the prompt prose — "set `value` to `null`" became
  // "set `value` to `None`" — a prompt that no longer matched
  // engine/prompts/_preamble.md, with a green build.
  //
  // Reading the generated node back and comparing it to the sources is the only
  // thing that catches either.
  // -------------------------------------------------------------------------
  describe('16 Build classifier requests, as generated', () => {
    const generated = classifierRequestCode();

    test('no generation marker survives into the node', () => {
      assert.doesNotMatch(generated, /@@[A-Z_]+@@/, 'a placeholder was not substituted');
    });

    test('the model is the policy model, and no Clay-native model appears', () => {
      assert.match(generated, new RegExp(`MODEL = "${MODELS.classifier}"`));
      assert.doesNotMatch(generated, /claude-/i);
      assert.doesNotMatch(generated, /luna/i);
      assert.doesNotMatch(generated, /gpt-5\.4-nano/i);
    });

    test('PROMPTS and SCHEMAS evaluate to the repository sources, exactly',
      { skip: !python3 }, () => {
        const probe = `
${generated}

import json as _json
print(_json.dumps({"prompts": PROMPTS, "schemas": SCHEMAS}))
`;
        const out = execFileSync(python3, ['-c', 'import sys; exec(sys.stdin.read())'], {
          input: probe, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
        });
        const { prompts, schemas } = JSON.parse(out);

        for (const [component] of COMPONENTS) {
          assert.equal(
            prompts[component], classifierPrompt(component),
            `${component}: the prompt inside the node is not the one built from engine/prompts/`,
          );
          // The preamble's own words, intact — the canary for textual rewriting.
          assert.match(
            prompts[component], /set `value` to `null`/,
            `${component}: the prompt text was altered in transit`,
          );
          assert.deepEqual(
            schemas[component], STRICT_SCHEMAS[component],
            `${component}: the strict schema inside the node is not the generated one`,
          );
          assert.equal(
            typeof schemas[component], 'object',
            `${component}: the schema is a ${typeof schemas[component]}, not an object — `
            + 'OpenAI rejects a stringified schema with ERROR_ACTION_RUNTIME_ERROR',
          );
          assert.equal(schemas[component].strict, true);
        }
      });

    test('every component in the rubric has a prompt and a schema', () => {
      assert.equal(COMPONENTS.length, 7);
      for (const [component] of COMPONENTS) {
        assert.ok(STRICT_SCHEMAS[component], `${component} has no strict schema`);
        assert.ok(classifierPrompt(component).length > 500, `${component}: prompt looks truncated`);
      }
    });
  });

  test('no tool node pins a property that is not an action parameter', () => {
    // A tool node's inputSchema is NOT "silently dropped on save" when it
    // carries a property of our own, whatever the docs say: the property
    // persists and the action then throws ERROR_ACTION_RUNTIME_ERROR at run
    // time, with no status, no message and no parameter name. The Authorization
    // header therefore rides inside `headers`, which is a real action
    // parameter, built by the code node upstream.
    //
    // HTTP_API_PARAMS is `clay workflows actions schema 4299091f-… http-api-v2`
    // as of 2026-09-15.
    const HTTP_API_PARAMS = new Set([
      'method', 'url', 'queryString', 'body', 'headers', 'fieldPaths',
      'removeNull', 'returnResponseMetadata', 'followRedirects',
      'followRedirectsOptions', 'responseTimeout', 'shouldRetry', 'retryOptions',
    ]);
    for (const node of NODES) {
      if (node.spec.nodeType !== 'tool') continue;
      const action = node.spec.tools?.[0]?.actionKey;
      if (action !== 'http-api-v2') continue;
      for (const key of Object.keys(node.spec.inputSchema?.properties ?? {})) {
        assert.ok(
          HTTP_API_PARAMS.has(key.split('|')[0]),
          `${node.spec.name} pins "${key}", which is not an http-api-v2 parameter — `
          + 'the action will throw ERROR_ACTION_RUNTIME_ERROR at run time',
        );
      }
    }
  });

  test('every OpenAI request body is built in a code node, never a static', () => {
    // The key must not be a literal in a node's static config. Building the
    // headers upstream keeps it in n8n's credential store and out of both this
    // repository and the canvas.
    for (const node of NODES) {
      if (node.spec.nodeType !== 'tool') continue;
      const mapping = node.spec.tools?.[0]?.inputMappingConfig ?? {};
      if (mapping.url?.value !== 'https://api.openai.com/v1/chat/completions') continue;
      assert.equal(mapping.body?.type, 'reference', `${node.spec.name}: body must be a reference`);
      // `headers` must NOT be in the mapping at all. An object-valued action
      // parameter passed as a reference makes the action throw
      // ERROR_ACTION_RUNTIME_ERROR at run time; supplied by the pin alone, the
      // identical headers arrive intact. Measured both ways.
      assert.equal(
        mapping.headers, undefined,
        `${node.spec.name}: headers must come from the pin, not from inputMappingConfig`,
      );
      assert.ok(
        node.spec.inputSchema?.properties?.headers?.sourcePath,
        `${node.spec.name}: headers must be pinned from the code node upstream`,
      );
    }
  });

  test('08_build_summary_request.py still has its model marker', () => {
    assert.match(readText('clay', 'code', '08_build_summary_request.py'), /@@SUMMARY_MODEL@@/);
  });

  test('no LLM request sends `temperature` — the GPT-5.6 family rejects it', () => {
    // HTTP 400: "Unsupported value: 'temperature' does not support 0 with this
    // model. Only the default (1) value is supported." Sending it fails the
    // call outright, so this is a build-breaking mistake, not a style rule.
    for (const file of ['08_build_summary_request.py', '16_build_classifier_requests.py']) {
      const source = readText('clay', 'code', file);
      const uncommented = source.split('\n').filter((l) => !l.trim().startsWith('#')).join('\n');
      assert.doesNotMatch(
        uncommented, /"temperature"\s*:/,
        `${file} sends temperature, which the GPT-5.6 family rejects with HTTP 400`,
      );
      assert.match(uncommented, /"seed"\s*:\s*0/, `${file} must pin seed 0`);
    }
  });
});
