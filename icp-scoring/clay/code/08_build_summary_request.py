# 08 Build website summary request
#
# Clay code nodes cannot make network calls — `urllib` is not importable and the
# node runtime has no `context.call_tool` (see clay/WORKFLOW.md). So every LLM
# call in this workflow is an `http-api-v2` tool node, and a code node's job is
# to build the request body and, downstream, to read the reply.
#
# The model policy is OpenAI-only on the workspace's own key: summarization runs
# on Terra, classification on Sol. Neither is a Clay-native Claygent.

import json

MODEL = "@@SUMMARY_MODEL@@"

SYSTEM = (
    "You summarize a company website for an ICP scoring engine. You are factual, "
    "you never add anything the pages do not say, and you never score or recommend."
)

INSTRUCTIONS = """Write a factual summary of {company} from the page text below.

Cover, when the pages say it:

- what the company sells, in its own words;
- whether software is the product, or supports a non-software product;
- who it sells to, and at what size;
- any engineering hiring, team growth or capacity language on /careers;
- any roadmap, platform-rebuild or re-platforming language on /product.

Rules:

- Use only the page text below. Never add anything you know about the company
  from elsewhere — a fact not on these pages is not evidence, and using it makes
  the score unreproducible for the next person who looks at the row.
- Do not infer revenue, headcount or funding. Other enrichment supplies those.
- Say plainly which pages were not reachable. Pages reachable: {reachable}.
- Under 300 words. No marketing tone, no recommendation, no score.

---

{page_text}"""


def handler(context):
    page_text = context.get_input("page_text")
    # The Authorization header is built HERE, in a code node, rather than
    # pinned onto the HTTP node. A tool node's inputSchema accepts only the
    # action's own parameters: adding `openai_api_key` to it does not get
    # "silently dropped" as the docs say, it makes the action throw
    # ERROR_ACTION_RUNTIME_ERROR at run time with no further detail. `headers`
    # IS an action parameter, and a single-expression reference passes a whole
    # object through, so the key rides inside it. See clay/WORKFLOW.md.
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer %s" % (context.get_input("openai_api_key") or ""),
    }

    if not page_text or not str(page_text).strip():
        # Nothing was scraped. Emit no request at all rather than paying for a
        # call that can only answer "there was no text".
        return {"summary_request": None, "should_call": False, "headers": headers}

    body = {
        "model": MODEL,
        # `temperature` is deliberately absent. The GPT-5.6 family rejects
        # temperature 0 outright ("Only the default (1) value is supported"),
        # so sending it would 400 the call. See clay/WORKFLOW.md.
        "seed": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": INSTRUCTIONS.format(
                company=context.get_input("company_name") or "this company",
                reachable=context.get_input("pages_reachable") or "unknown",
                page_text=str(page_text),
            )},
        ],
    }
    return {
        "summary_request": json.dumps(body, ensure_ascii=False),
        "should_call": True,
        "model": MODEL,
        "headers": headers,
    }
