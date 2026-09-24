# 22 Build icp.scored event
#
# The exact body POSTed to n8n Path B, shaped by
# engine/schemas/icp_scored_event.schema.json. That schema is
# `additionalProperties: false` at every level, so this node builds the key set
# literally and adds nothing: an unexpected key is meant to fail loudly at the
# n8n boundary, and it can only do that if this node does not invent keys.
#
# Path B dedupes on `event_id`, which is what makes the "3x retry on 5xx" policy
# on the POST safe — a retry that actually landed the first time writes nothing
# the second time.

import json
import time

CLAY_TABLE_LABEL = "ICP_Engine v5 [DEV] (Clay Workflow)"


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _run_id(context, request_id):
    """This run's id, for use as the Path B dedupe key.

    Clay's code sandbox does not expose the run id through a documented
    accessor; it appears inside the private callback URL the sandbox is handed
    (.../workflow-run/<runId>/step/<stepId>). That is read here defensively —
    if the shape ever changes, the fallback is the n8n correlation id, which is
    already unique per scoring request and is exactly as good a dedupe key.
    """
    try:
        url = getattr(context, "_callback_url", None)
        if isinstance(url, str) and "/workflow-run/" in url:
            candidate = url.split("/workflow-run/", 1)[1].split("/", 1)[0].strip()
            if len(candidate) >= 8:
                return candidate
    except Exception:
        pass
    return "req-%s" % request_id if request_id else None


def handler(context):
    request_id = _text(context.get_input("request_id"))
    score = context.get_input("score") or {}
    components = context.get_input("components") or {}
    facts_summary = context.get_input("facts_summary") or {}

    event = {
        "event": "icp.scored",
        "event_id": _run_id(context, request_id),
        "request_id": request_id,
        # `datetime` is not importable in Clay's code-node runtime (REPORT.md),
        # so the ISO 8601 stamp is formatted from `time` directly. UTC, always.
        "emitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_version": "v5",

        "org_id": _text(context.get_input("org_id")),
        "deal_id": _text(context.get_input("deal_id")),

        "identifier_kind": _text(context.get_input("identifier_kind")),
        "identifier_value": _text(context.get_input("identifier_value")),

        "components": components,
        "score": score,
        "facts_summary": {
            "revenue_usd": facts_summary.get("revenue_usd"),
            "headcount_total": facts_summary.get("headcount_total"),
            "headcount_eng": facts_summary.get("headcount_eng"),
        },

        "clay_table": CLAY_TABLE_LABEL,
        "clay_row_url": None,
    }

    return {
        "event": event,
        # http-api-v2's Body parameter is longtext, so the POST sends this
        # string rather than the object.
        "event_json": json.dumps(event, ensure_ascii=False),
        "callback_url": _text(context.get_input("callback_url")),
        # No X-Clay-Secret. Owner's ruling: the unguessable Path B webhook path
        # IS the control, and a shared-secret header that has to live somewhere
        # Clay can read it buys nothing on top of that — Clay has no
        # CLI-reachable secret store, so the header would have been a literal in
        # a node's config, which is a worse place for a secret than no secret.
        #
        # What the path being the credential actually requires: it never appears
        # in this repository (it is read from ICP_WEBHOOK_PATH_B at build time),
        # never in a log, and never in a run trace that leaves the workspace.
        "headers": {
            "Content-Type": "application/json",
        },
        # Flattened onto the node output so the run trace is readable without
        # opening the payload.
        "grade": score.get("grade"),
        "final_score": score.get("final_score"),
        "status": score.get("status"),
        "confidence_overall": score.get("confidence_overall"),
    }
