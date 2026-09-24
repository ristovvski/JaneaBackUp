# 23 Collect classifier outputs
#
# Reads the seven OpenAI replies and turns them into the `components` object
# that engine/schemas/icp_scored_event.schema.json defines.
#
# Strict mode guarantees the JSON parses and matches the schema it was given, so
# this node does not re-validate the shape. What it DOES enforce is the two
# limits strict mode cannot express — `evidence` at most 6 items, each at most
# 200 characters — and the rule that anything missing reads as low confidence.
# A component whose call failed becomes a real null with confidence "low" and a
# missing_inputs entry naming the failure, so the scorer gates on it exactly as
# it would on an honest "I could not tell".

import json

COMPONENTS = [
    "industry_vertical", "stage_maturity", "company_type",
    "geography", "revenue_range", "activation_state", "buying_signal",
]

MAX_EVIDENCE_ITEMS = 6
MAX_EVIDENCE_CHARS = 200


def _content(raw):
    """The assistant's JSON string out of a chat-completions response."""
    body = raw
    if isinstance(body, list):
        body = body[0] if body else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _strings(value, limit_items, limit_chars):
    if not isinstance(value, list):
        return []
    out = []
    for entry in value[:limit_items]:
        text = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
        out.append(text[:limit_chars])
    return out


def _component(name, parsed):
    if parsed is None:
        # The call failed, or returned something unparseable. Say so in the
        # component itself: null value, low confidence, and a missing_inputs
        # entry a human can act on.
        return {
            "value": None,
            "evidence": [],
            "confidence": "low",
            "missing_inputs": ["classifier_call_failed:%s" % name],
        }

    entry = {
        "value": parsed.get("value"),
        "evidence": _strings(parsed.get("evidence"), MAX_EVIDENCE_ITEMS, MAX_EVIDENCE_CHARS),
        "confidence": parsed.get("confidence") if parsed.get("confidence") in ("high", "medium", "low") else "low",
        "missing_inputs": _strings(parsed.get("missing_inputs"), 50, 200),
    }
    if name == "activation_state":
        months = parsed.get("evidence_dated_within_months")
        entry["evidence_dated_within_months"] = months if isinstance(months, int) and not isinstance(months, bool) else None
    return entry


def handler(context):
    components = {}
    failed = []
    for name in COMPONENTS:
        parsed = _content(context.get_input("reply_" + name))
        if parsed is None:
            failed.append(name)
        components[name] = _component(name, parsed)

    # --- the revenue conflict downgrade ----------------------------------
    #
    # When the two revenue providers landed two or more bands apart, node 15
    # took the lower figure and set this flag. The classifier is TOLD about the
    # conflict — it is spelled out in `revenue_source`, which every prompt
    # instructs the model to cite — but being told is not the same as being
    # bound. A model that reads the conflict and still answers "high" would put
    # a confident number behind a figure two providers cannot agree on, and
    # revenue_range gates the whole score.
    #
    # So the downgrade happens here, in code, unconditionally. The evidence line
    # says why, so the reason survives into the Pipedrive note and the audit row
    # rather than looking like an unexplained low.
    if context.get_input("revenue_conflict") is True:
        entry = components["revenue_range"]
        entry["confidence"] = "low"
        note = "revenue_source: providers 2+ bands apart, lower band taken"
        if note not in entry["evidence"]:
            entry["evidence"] = ([note] + entry["evidence"])[:MAX_EVIDENCE_ITEMS]

    return {
        "components": components,
        "classifiers_failed": ",".join(failed) if failed else "",
        "classifiers_ok": len(COMPONENTS) - len(failed),
        "revenue_downgraded": context.get_input("revenue_conflict") is True,
    }
