# 01 Prepare enrichment inputs
#
# n8n already normalized every identifier before it POSTed (engine/normalize.mjs
# -> n8n/nodes/BuildClayRequest.js), and clay_table_spec.md is explicit that
# "Clay never has to agree with n8n about what a domain is". So this node does
# NOT re-normalize. It reads the Path A webhook body, decides whether there is
# anything worth spending an enrichment credit on, and hands that decision to
# the gate downstream.
#
# Every webhook key is read here rather than pinned separately on each later
# node, so the request's identity (request_id, org_id, callback_url) travels the
# graph from one place.

WEBHOOK_KEYS = [
    "request_id",
    "org_id",
    "deal_id",
    "identifier_kind",
    "identifier_value",
    "domain",
    "linkedin_url",
    "company_name",
    "hq_country",
    "hq_state",
    "model_version",
    "callback_url",
    # Not in clay_table_spec.md's twelve. Clay has no CLI-reachable secret store
    # and a code node has no network egress, so the OpenAI calls run from
    # `http-api-v2` tool nodes whose Authorization header references this value.
    # It lives in n8n's credential store and travels per request; it is never in
    # this repository and never in a node's static config. See clay/WORKFLOW.md.
    "openai_api_key",
]


def _blank(value):
    """A key n8n sent as null, or as whitespace, is absent."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def handler(context):
    out = {}
    for key in WEBHOOK_KEYS:
        value = context.get_input(key)
        out[key] = None if _blank(value) else value

    # cpj-enrich-company accepts a LinkedIn company URL or a domain, and its own
    # schema says "Use Company LinkedIn URL for highest accuracy" — so LinkedIn
    # wins when we hold both.
    out["company_identifier"] = out["linkedin_url"] or out["domain"]

    # The gate downstream reads this. False means: no domain, no LinkedIn, and
    # therefore nothing any provider can look up. The run still scores (from
    # name + HQ, at low confidence) — it just spends zero enrichment credits
    # doing it. That is NEEDS_DECISION #5's stated default.
    out["enrichable"] = bool(out["company_identifier"])

    # The company-profile node runs in list mode over this one-element list.
    # That is not a fan-out: it is the only way a Clay tool node survives its
    # provider failing (`listFailureMode: ignore_errors`). Without it, one
    # provider outage loses the whole score — which is strictly worse than the
    # table, where a failed enrichment column just leaves the cell empty.
    out["identifier_list"] = [out["company_identifier"]] if out["enrichable"] else []

    return out
