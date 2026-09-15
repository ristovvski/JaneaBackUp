# engine/clay_score.py
#
# GENERATED from config/rubric_v5.json by scripts/gen_clay_python.mjs — model v5.
# Do not hand-edit. Regenerate with `npm run gen:python`.
#
# This is the Clay Workflow "Score" code node. Clay code nodes run Python, so
# this is a PORT of engine/clay_formula.txt (JavaScript), not the same bytes.
# tests/contract/python_parity.test.mjs asserts the two produce deep-equal
# output over the golden fixtures and 500 generated inputs. Behaviour is
# proven identical; the source language is not the same, and that gap is
# recorded in REPORT.md.

RUBRIC = {
    "model_version": "v5",
    "weights": {"industries":15,"stage_maturity":25,"revenue_range":25,"company_type":25,"geography":10,"buying_signal":0},
    "levels": [0,3,7,10],
    "thresholds": {"A":75,"B":55},
    "multipliers": {"Accelerating":1,"Transitioning":1,"Stable":0.85,"Contracting":0},
    "activation_default": "Stable",
    "contracting_max_age_months": 12,
    "gating": ["stage_maturity","revenue_range","company_type"],
    "tier2": {"revenue_usd_gt":500000000,"headcount_gt":1000,"company_type_level_eq":7},
    "vertical_level": {"FinTech":10,"HealthTech / MedTech":10,"SportsTech":7,"Analytics / ML":7,"Data Platform SaaS":7,"SaaS — Other":7,"Manufacturing tech / Industrial IoT":3,"Enterprise Tech / Hyperscalers":10,"Pharma / Life Sciences":7,"EdTech":0,"LegalTech":0,"ClimaTech":3,"Government / Public Sector":0,"Pure Hardware / Consumer Electronics":0,"Telecom / 5G Infrastructure":0,"E-commerce / Retail Tech":0,"Pre-product Startups":0},
    "vertical_tier": {"FinTech":"Anchor","HealthTech / MedTech":"Anchor","SportsTech":"Watch","Analytics / ML":"Watch","Data Platform SaaS":"Watch","SaaS — Other":"Watch","Manufacturing tech / Industrial IoT":"Opportunistic","Enterprise Tech / Hyperscalers":"Anchor","Pharma / Life Sciences":"Watch","EdTech":"Out","LegalTech":"Out","ClimaTech":"Opportunistic","Government / Public Sector":"Out","Pure Hardware / Consumer Electronics":"Out","Telecom / 5G Infrastructure":"Out","E-commerce / Retail Tech":"Out","Pre-product Startups":"Out"},
}

WEIGHT_KEY_TO_LEVEL_KEY = {
    "industries": "industry",
    "stage_maturity": "stage_maturity",
    "revenue_range": "revenue_range",
    "company_type": "company_type",
    "geography": "geography",
    "buying_signal": "buying_signal",
}

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _round_half_up(x):
    """Half-up to an integer.

    Mirrors roundHalfUp in engine/scoring.mjs: collapse to 10 decimal places
    first so a .5 boundary reached through float arithmetic (74.50249999999998)
    still rounds up, without dragging 74.4 up with it. Python's built-in round()
    is banker's rounding and would send 74.5 to 74 — a silent grade change.
    """
    if x is None:
        return None
    collapsed = float("%.10f" % x)
    import math
    return int(math.floor(collapsed + 0.5))


def _resolve_level(raw):
    if raw is None:
        return 0
    if raw not in RUBRIC["levels"]:
        raise ValueError("level %s is not one of %s" % (repr(raw), RUBRIC["levels"]))
    return raw


def score(inputs):
    flags = []
    levels = (inputs or {}).get("levels") or {}
    confidence = (inputs or {}).get("confidence") or {}
    missing_inputs = (inputs or {}).get("missing_inputs") or {}
    facts = (inputs or {}).get("facts_summary") or {}

    # --- industry vertical -> level --------------------------------------
    vertical = (inputs or {}).get("industry_vertical")
    known = vertical is not None and vertical in RUBRIC["vertical_level"]
    industry_level = RUBRIC["vertical_level"][vertical] if known else 0
    industry_tier = RUBRIC["vertical_tier"][vertical] if known else None
    industry_confidence = confidence.get("industry_vertical")
    if not known:
        flags.append("unknown_vertical")
        industry_confidence = "low"

    levels_used = {
        "industry": industry_level,
        "stage_maturity": _resolve_level(levels.get("stage_maturity")),
        "company_type": _resolve_level(levels.get("company_type")),
        "geography": _resolve_level(levels.get("geography")),
        "revenue_range": _resolve_level(levels.get("revenue_range")),
        "buying_signal": _resolve_level(levels.get("buying_signal")),
    }

    # --- composite --------------------------------------------------------
    composite = 0.0
    for weight_key, weight in RUBRIC["weights"].items():
        composite += (weight * levels_used[WEIGHT_KEY_TO_LEVEL_KEY[weight_key]]) / 10.0
    composite = float("%.10f" % composite)
    if composite == int(composite):
        composite = int(composite)

    # --- activation state -------------------------------------------------
    activation_state_used = (inputs or {}).get("activation_state") or RUBRIC["activation_default"]
    if activation_state_used == "Contracting":
        age = (inputs or {}).get("activation_evidence_dated_within_months")
        dated = isinstance(age, (int, float)) and not isinstance(age, bool) \
            and age <= RUBRIC["contracting_max_age_months"]
        if not dated:
            activation_state_used = RUBRIC["activation_default"]
            flags.append("contracting_without_dated_evidence")

    if activation_state_used not in RUBRIC["multipliers"]:
        raise ValueError('unknown activation_state "%s"' % activation_state_used)
    multiplier = RUBRIC["multipliers"][activation_state_used]

    final_score = _round_half_up(composite * multiplier)
    final_score_without_activation = _round_half_up(composite)

    # --- insufficient data ------------------------------------------------
    insufficient = []
    for component in RUBRIC["gating"]:
        level = levels.get(component)
        if level is None:
            insufficient.append(component)
            continue
        missing = missing_inputs.get(component)
        if confidence.get(component) == "low" and isinstance(missing, list) and len(missing) > 0:
            insufficient.append(component)
    status = "insufficient_data" if insufficient else "scored"
    if insufficient:
        flags.append("insufficient:" + ",".join(insufficient))

    # --- grade ------------------------------------------------------------
    grade = None
    if status != "insufficient_data":
        if final_score >= RUBRIC["thresholds"]["A"]:
            grade = "A"
        elif final_score >= RUBRIC["thresholds"]["B"]:
            grade = "B"
        else:
            grade = "C"

    # --- overall confidence over the weighted components ------------------
    weighted = []
    for key, weight in RUBRIC["weights"].items():
        if weight > 0:
            weighted.append("industry_vertical" if key == "industries" else key)
    worst = "high"
    for component in weighted:
        label = industry_confidence if component == "industry_vertical" else confidence.get(component)
        effective = label if label in CONFIDENCE_RANK else "low"
        if CONFIDENCE_RANK[effective] < CONFIDENCE_RANK[worst]:
            worst = effective

    # --- tier 2 -----------------------------------------------------------
    revenue = facts.get("revenue_usd")
    headcount = facts.get("headcount_total")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    tier2_candidate = bool(
        (num(revenue) and revenue > RUBRIC["tier2"]["revenue_usd_gt"])
        or (num(headcount) and headcount > RUBRIC["tier2"]["headcount_gt"])
        or levels_used["company_type"] == RUBRIC["tier2"]["company_type_level_eq"]
    )
    if tier2_candidate:
        flags.append("tier2_candidate")

    buying = levels.get("buying_signal")
    return {
        "model_version": RUBRIC["model_version"],
        "industry_level": industry_level,
        "industry_tier": industry_tier,
        "levels_used": levels_used,
        "buying_signal_level": buying if buying is not None else None,
        "composite": composite,
        "activation_state_used": activation_state_used,
        "multiplier": multiplier,
        "final_score": final_score,
        "final_score_without_activation": final_score_without_activation,
        "grade": grade,
        "status": status,
        "confidence_overall": worst,
        "tier2_candidate": tier2_candidate,
        "flags": flags,
    }
