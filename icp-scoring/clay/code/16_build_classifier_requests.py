# 15 Build classifier requests
#
# One OpenAI chat-completions body per component — seven of them, each carrying
# its own prompt and its own strict-mode JSON schema. The seven tool nodes
# downstream each send exactly one of these, so a single bad component fails and
# retries alone, which is what clay_table_spec.md section 7 asks for.
#
# PROMPTS and SCHEMAS below are GENERATED into this file by
# clay/build_workflow.mjs from engine/prompts/*.md and
# engine/schemas/openai/*.strict.json. A Clay code node cannot read this
# repository at run time, so the only way the canvas can be provably identical
# to the sources is to inline them and diff on every build — which the builder's
# verification pass does.

import json

MODEL = "@@CLASSIFIER_MODEL@@"

# @@GENERATED@@


def handler(context):
    facts_json = context.get_input("facts_json")
    if not facts_json:
        raise ValueError("15 Build classifier requests: facts_json is empty — node 13 produced nothing")

    out = {"model": MODEL, "components": list(PROMPTS.keys())}
    for component, prompt in PROMPTS.items():
        body = {
            "model": MODEL,
            # No `temperature`. The GPT-5.6 family rejects temperature 0 with
            # HTTP 400 ("Only the default (1) value is supported"), so the
            # determinism the rubric asks for is pursued through a fixed seed
            # and a closed output schema instead. This gap is recorded in
            # clay/WORKFLOW.md rather than papered over.
            "seed": 0,
            "response_format": {"type": "json_schema", "json_schema": SCHEMAS[component]},
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Classify the component `%s` for this company.\n\n"
                        "This is the complete fact set. Nothing outside it is evidence.\n\n"
                        "```json\n%s\n```" % (component, facts_json)
                    ),
                },
            ],
        }
        out["body_" + component] = json.dumps(body, ensure_ascii=False)
    return out
