

# ---------------------------------------------------------------------------
# 24 Score (ICP v5) — Clay code-node handler
#
# Everything above this line is engine/clay_score.py, generated from
# config/rubric_v5.json by scripts/gen_clay_python.mjs and asserted deep-equal
# to engine/scoring.mjs over the golden fixtures and 500 generated inputs by
# tests/contract/python_parity.test.mjs. It is embedded verbatim; nothing below
# changes a number.
#
# This handler is the Python equivalent of STEP 1 + STEP 2 of
# engine/clay_formula.txt: take the seven classifier outputs and shape them into
# the one `inputs` object score() expects.
#
# Since the classifiers run under OpenAI strict structured outputs, a level
# arrives as a real number and a null arrives as a real null — no select-string
# decoding, no JSON-in-a-string. The only defensiveness left here is against a
# component whose call failed upstream, which node 23 already renders as
# value null / confidence low.
# ---------------------------------------------------------------------------

LEVEL_COMPONENTS = ("stage_maturity", "company_type", "geography", "revenue_range", "buying_signal")
ALL_COMPONENTS = ("industry_vertical",) + LEVEL_COMPONENTS + ("activation_state",)


def _level(raw):
    """A level the rubric recognises, or None. Never a guess."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)) and int(raw) in RUBRIC["levels"] and float(raw) == int(raw):
        return int(raw)
    return None


def _label(raw):
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return None if text == "" or text.lower() == "null" else text


def _confidence(raw):
    """Anything the classifier did not say is low. Never silently high."""
    text = str(raw or "").strip().lower()
    return text if text in CONFIDENCE_RANK else "low"


def _list_of_strings(raw):
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _months(raw):
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def handler(context):
    raw = context.get_input("components") or {}

    components = {}
    for name in ALL_COMPONENTS:
        entry = raw.get(name) if isinstance(raw.get(name), dict) else {}
        value = entry.get("value")
        components[name] = {
            "value": _label(value) if name in ("industry_vertical", "activation_state") else _level(value),
            "evidence": _list_of_strings(entry.get("evidence"))[:6],
            "confidence": _confidence(entry.get("confidence")),
            "missing_inputs": _list_of_strings(entry.get("missing_inputs")),
        }
    components["activation_state"]["evidence_dated_within_months"] = _months(
        (raw.get("activation_state") or {}).get("evidence_dated_within_months")
    )

    facts_summary = {
        "revenue_usd": context.get_input("revenue_usd"),
        "headcount_total": context.get_input("headcount_total"),
        "headcount_eng": context.get_input("headcount_eng"),
    }

    inputs = {
        "industry_vertical": components["industry_vertical"]["value"],
        "levels": {name: components[name]["value"] for name in LEVEL_COMPONENTS},
        "activation_state": components["activation_state"]["value"],
        "activation_evidence_dated_within_months":
            components["activation_state"]["evidence_dated_within_months"],
        "confidence": {
            name: components[name]["confidence"]
            for name in ("industry_vertical",) + LEVEL_COMPONENTS
        },
        "missing_inputs": {
            name: components[name]["missing_inputs"]
            for name in ("industry_vertical",) + LEVEL_COMPONENTS
        },
        "facts_summary": facts_summary,
    }

    return {
        "score": score(inputs),
        "components": components,
        "facts_summary": facts_summary,
    }
