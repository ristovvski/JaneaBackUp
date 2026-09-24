# 13 Build facts_json
#
# The object every one of the seven classifiers reads. Its shape is fixed by
# engine/schemas/enrichment_facts.schema.json: 25 required keys plus deal_id,
# `additionalProperties: false`.
#
# The one rule that matters more than any other here:
#
#   NULLS ARE KEPT AS NULL. Never 0, never "", never "unknown".
#
# The classifier preamble tells the model to read null as "enrichment did not
# find it" and an empty array as "we looked and found nothing". Coercing a null
# to 0 turns "we do not know the revenue" into "pre-revenue", which is the
# difference between Insufficient data and a confidently wrong grade.
#
# Every key is present on every row even when the branch that would have filled
# it never ran — a request with no domain reaches this node with all sixteen
# enrichment inputs unset, and still produces a well-formed fact set.

import json
import time

FACT_KEYS = [
    "request_id", "org_id", "deal_id", "identifier_kind", "identifier_value",
    "domain", "linkedin_url", "company_name", "hq_country", "hq_state",
    "li_headcount", "li_industry", "li_description", "li_founded", "li_hq",
    "website_summary", "revenue_estimate_usd", "revenue_source",
    "funding_stage", "last_round_date", "last_round_usd",
    "open_eng_roles_count", "eng_roles_open_60d_plus", "senior_eng_roles",
    "eng_headcount_estimate", "news_last_12mo", "captured_at",
]

ENGINEERING_WORDS = (
    "engineer", "engineering", "software", "developer", "development",
    "devops", "sre", "platform", "backend", "back-end", "frontend",
    "front-end", "full stack", "fullstack", "data science", "machine learning",
    "architect", "programmer", "qa ", "quality assurance", "technology",
)

SENIOR_WORDS = (
    "staff", "principal", "lead", "head of", "director", "vp ",
    "vice president", "chief", "cto", "distinguished", "architect",
)


def _blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _text(value):
    return None if _blank(value) else str(value).strip()


def _int(value):
    if _blank(value) or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _number(value):
    if _blank(value) or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _list(value):
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Revenue, when the provider answers with a band
#
# The company-profile lookup does not return a number: it returns a string like
# "10M-25M". `enrichment_facts.schema.json` types `revenue_estimate_usd` as
# number-or-null and closes `additionalProperties`, so there is nowhere to put
# the band itself — and dropping it to null would leave `revenue_range` (a
# gating component) unanswerable on a company whose revenue we do in fact have
# an estimate for.
#
# So the band is reduced to its MIDPOINT and the raw band text is carried in
# `revenue_source`, which every classifier is instructed to cite by key. A
# reviewer reading the evidence line sees `revenue_source: Company profile
# lookup (band "10M-25M")` and knows exactly how precise the number is.
#
# This is not the headcount-derived revenue the prompt forbids. It is the
# provider's own revenue estimate, expressed less precisely than a scalar.
# ---------------------------------------------------------------------------

_MULTIPLIER = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def _scalar(token):
    """"$1.5B" / "25M" / "500000" -> a float. None if it is not a magnitude."""
    text = str(token).strip().lower().replace("$", "").replace(",", "").replace("+", "")
    if text == "":
        return None
    factor = 1.0
    if text[-1] in _MULTIPLIER:
        factor = _MULTIPLIER[text[-1]]
        text = text[:-1]
    try:
        return float(text) * factor
    except ValueError:
        return None


# The band ladder. Two providers "disagreeing" needs a unit, and the natural one
# is not a ratio — it is how many standard revenue brackets apart they land. A
# ladder makes "two bands apart" mean the same thing at $10M and at $10B, which
# a ratio does not.
_BANDS = [
    (1e6, "<$1M"), (1e7, "$1M-$10M"), (2.5e7, "$10M-$25M"), (5e7, "$25M-$50M"),
    (1e8, "$50M-$100M"), (2.5e8, "$100M-$250M"), (5e8, "$250M-$500M"),
    (1e9, "$500M-$1B"), (1e10, "$1B-$10B"), (1e11, "$10B-$100B"),
]

# Two or more bands apart is the threshold at which the lower figure is taken
# rather than the primary provider's. One band apart is ordinary provider noise
# and the primary still wins.
_CONFLICT_BANDS = 2


def _band_index(usd):
    """Which bracket a figure falls in. The top band is open-ended."""
    if usd is None:
        return None
    for index, (ceiling, _label) in enumerate(_BANDS):
        if usd < ceiling:
            return index
    return len(_BANDS)


def _band_label(usd):
    index = _band_index(usd)
    if index is None:
        return None
    return _BANDS[index][1] if index < len(_BANDS) else ">$100B"


def _revenue(value):
    """(usd, band_text). `usd` is the midpoint for a band, the value for a scalar."""
    if _blank(value):
        return None, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), None

    raw = str(value).strip()
    parts = [p for p in raw.replace("\u2013", "-").replace("\u2014", "-").split("-") if p.strip()]
    numbers = [n for n in (_scalar(p) for p in parts) if n is not None]
    if not numbers:
        return None, None
    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2.0, raw
    return numbers[0], (raw if raw != str(numbers[0]) else None)


# ---------------------------------------------------------------------------
# Dates, without `datetime`.
#
# Clay's code-node runtime allows a short list of modules and `datetime` is not
# on it (`json`, `time`, `math`, `re`, `os`, `sys`, `collections`, `itertools`,
# `functools`, `random`, `operator`, `copy`, `textwrap`, `typing` are; see
# REPORT.md). So the two windows the rubric needs — news inside 12 months, an
# engineering role open more than 60 days — are computed as integer day counts
# from the civil calendar directly.
#
# The conversion is Howard Hinnant's days_from_civil: exact for every proleptic
# Gregorian date, no floating point, no leap-year special cases at the call
# site. UTC throughout, because every date the providers return is a date, not
# a local timestamp.
# ---------------------------------------------------------------------------


def _days_from_civil(year, month, day):
    """Days since 1970-01-01 for a civil (y, m, d). Exact integer arithmetic."""
    year -= 1 if month <= 2 else 0
    era = (year if year >= 0 else year - 399) // 400
    yoe = year - era * 400                                   # [0, 399]
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy            # [0, 146096]
    return era * 146097 + doe - 719468


def _today_days():
    now = time.gmtime()
    return _days_from_civil(now.tm_year, now.tm_mon, now.tm_mday)


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _date(value):
    """The leading YYYY-MM-DD of an ISO 8601 string, as (days_since_epoch, text).

    None for anything that is not a calendar date — an undated item is not
    evidence the rubric can use, and silently treating it as today would let an
    undated layoff rumour zero out a score.
    """
    if _blank(value):
        return None
    text = str(value)[:10]
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    try:
        year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    except ValueError:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1800 <= year <= 2999):
        return None
    # A day-of-month that overruns the month (a provider sending "2026-02-30")
    # rolls forward rather than being rejected. That is at most a one-day skew
    # on an already-malformed date, inside windows of 60 and 365 days.
    return _days_from_civil(year, month, day), text


def _looks_engineering(job):
    haystack = " ".join(
        str(part).lower()
        for part in (
            job.get("title"),
            " ".join(str(c) for c in _list(job.get("categories"))),
            (job.get("onet_data") or {}).get("family") if isinstance(job.get("onet_data"), dict) else None,
        )
        if part
    )
    return any(word in haystack for word in ENGINEERING_WORDS)


def _looks_senior(job):
    haystack = "%s %s " % (str(job.get("title") or "").lower(), str(job.get("seniority") or "").lower())
    return any(word in haystack for word in SENIOR_WORDS)


def _summarize_jobs(jobs, today, provider_ran):
    """open_eng_roles_count / eng_roles_open_60d_plus / senior_eng_roles.

    Returns (None, None, None) only when the jobs provider never ran. When it
    ran and found nothing the answer is (0, 0, 0) — "we looked, there are no
    open engineering roles" is a fact the stage_maturity classifier uses, and
    it is a different fact from "we did not look". The provider returns
    `jobs: []` with a `domain` on a clean no-data result, so the presence of
    that domain is the ran-signal.
    """
    if not provider_ran:
        return None, None, None

    open_count = 0
    open_60d_plus = 0
    senior = 0
    for job in jobs:
        if not isinstance(job, dict) or not _looks_engineering(job):
            continue
        open_count += 1
        if _looks_senior(job):
            senior += 1
        first_seen = _date(job.get("first_seen_at"))
        if first_seen and (today - first_seen[0]) > 60:
            open_60d_plus += 1
    return open_count, open_60d_plus, senior


def _latest_financing(events):
    """The most recent financing event, by effective date then discovery date."""
    best = None
    best_when = None
    for event in events:
        if not isinstance(event, dict):
            continue
        when = _date(event.get("effective_date")) or _date(event.get("found_at"))
        if when is None:
            continue
        if best_when is None or when[0] > best_when[0]:
            best, best_when = event, when
    return best


def _news_within_12_months(events, today):
    """[{date, headline, source, url}], newest first, dated inside the window.

    Every item carries a date: activation_state cannot return Contracting
    without one, so an undated news item is worse than useless here. An empty
    list is meaningful — it says we looked and found nothing.
    """
    items = []
    for event in events:
        if not isinstance(event, dict):
            continue
        article = event.get("news_article_attributes")
        article = article if isinstance(article, dict) else {}
        when = (
            _date(event.get("effective_date"))
            or _date(article.get("published_at"))
            or _date(event.get("found_at"))
        )
        if when is None or (today - when[0]) > 365:
            continue
        headline = _text(article.get("title")) or _text(event.get("summary")) or _text(event.get("article_sentence"))
        if not headline:
            continue
        items.append({
            "date": when[1],
            "headline": headline[:300],
            "source": _text(event.get("category")),
            "url": _text(article.get("url")),
        })
    items.sort(key=lambda item: item["date"], reverse=True)
    return items[:25]


def handler(context):
    today = _today_days()
    facts = {}

    # --- straight from the webhook (10 keys) ------------------------------
    for key in ("request_id", "org_id", "deal_id", "identifier_kind",
                "identifier_value", "linkedin_url", "company_name",
                "hq_country", "hq_state"):
        facts[key] = _text(context.get_input(key))

    # `domain` prefers what Pipedrive held; the profile lookup only fills a gap.
    facts["domain"] = _text(context.get_input("domain")) or _text(context.get_input("domain_for_enrichment"))

    # --- company profile lookup (node 03) ---------------------------------
    facts["li_headcount"] = _int(context.get_input("profile_employee_count"))
    facts["li_industry"] = _text(context.get_input("profile_industry"))
    facts["li_description"] = (
        _text(context.get_input("profile_description")) or _text(context.get_input("pdl_summary"))
    )
    facts["li_founded"] = _int(context.get_input("profile_founded"))
    hq_parts = [p for p in (_text(context.get_input("profile_locality")),
                            _text(context.get_input("profile_country"))) if p]
    facts["li_hq"] = ", ".join(hq_parts) if hq_parts else None

    # --- website (nodes 06-10) --------------------------------------------
    summary = _text(context.get_input("website_summary"))
    reachable = _text(context.get_input("website_pages_reachable"))
    if summary and reachable:
        summary = "%s\n\nPages reachable: %s" % (summary, reachable)
    facts["website_summary"] = summary

    # --- revenue and headcount (node 11, falling back to node 03) ---------
    # Primary is the firmographic provider's inferred revenue; the company
    # profile lookup's band is the fallback. Whichever wins, `revenue_source`
    # names it, and carries the band text when the figure came from one — so a
    # reviewer can see how precise the number behind a grade actually is.
    # ---------------------------------------------------------------------
    # Revenue, and what to do when the two providers disagree
    #
    # The primary stays primary. But its field is named `inferred_revenue` — a
    # model's estimate, not a reported figure — and on akuvo.com it read two
    # bands above the company profile lookup ($50M-$100M against $10M-$25M) on a
    # company with 90 people, founded 2019, $13M raised. The lower band was the
    # plausible one.
    #
    # So: one band apart is provider noise and the primary wins. TWO OR MORE
    # bands apart is a real disagreement, and the LOWER figure is taken. A
    # provider that reads high on small companies otherwise pushes borderline
    # accounts from B to A across the whole CRM, quietly, and the A threshold
    # has no margin underneath it.
    #
    # `revenue_conflict` travels downstream, where node 24 forces
    # revenue_range's confidence to low. Leaving that to the prompt would make
    # a rule out of a request.
    # ---------------------------------------------------------------------
    pdl_revenue, pdl_band = _revenue(context.get_input("pdl_revenue"))
    profile_revenue, profile_band = _revenue(context.get_input("profile_annual_revenue"))
    facts_conflict = False

    if pdl_revenue is not None:
        chosen, source = pdl_revenue, "Firmographic enrichment (inferred)"
        if pdl_band:
            source += ' (band "%s")' % pdl_band

        if profile_revenue is not None:
            gap = abs(_band_index(pdl_revenue) - _band_index(profile_revenue))
            other = "company profile lookup" + (
                ' (band "%s")' % profile_band if profile_band else " (%s)" % profile_revenue
            )
            if gap >= _CONFLICT_BANDS:
                facts_conflict = True
                chosen = min(pdl_revenue, profile_revenue)
                source = (
                    "CONFLICT: firmographic enrichment (inferred)%s and %s are %d bands apart; "
                    "taking the lower figure (%s) and treating revenue as low confidence"
                    % (
                        ' (band "%s")' % pdl_band if pdl_band else "",
                        other,
                        gap,
                        _band_label(chosen),
                    )
                )
            elif gap == 1:
                source += "; %s disagrees by one band" % other

        facts["revenue_estimate_usd"] = chosen
        facts["revenue_source"] = source
    elif profile_revenue is not None:
        facts["revenue_estimate_usd"] = profile_revenue
        facts["revenue_source"] = (
            "Company profile lookup" + (' (band "%s")' % profile_band if profile_band else "")
        )
    else:
        facts["revenue_estimate_usd"] = None
        facts["revenue_source"] = None

    facts["eng_headcount_estimate"] = _int(context.get_input("pdl_eng_headcount"))
    if facts["li_headcount"] is None:
        facts["li_headcount"] = _int(context.get_input("pdl_employee_count"))

    # --- financing (nodes 11 and 12) --------------------------------------
    #
    # Two sources that disagree about which round is the latest: the
    # financing-events provider is authoritative for the AMOUNT (it carries the
    # figure with its date) while the firmographic provider often knows about a
    # more recent round and names its STAGE.
    #
    # The rule is that the stage and the date must describe the SAME round. The
    # newer date wins outright, and the amount is only carried when the round it
    # belongs to is the one that won. Mixing them — a 2025 stage against a 2023
    # date — reads to stage_maturity as one coherent fact, and is not one.
    financing = _latest_financing(_list(context.get_input("financing_events")))
    events_date = None
    if financing:
        events_date = _date(financing.get("effective_date")) or _date(financing.get("found_at"))
    firmographic_date = _date(context.get_input("pdl_last_funding_date"))
    firmographic_stage = _text(context.get_input("pdl_funding_stage"))

    use_firmographic = (
        firmographic_date is not None
        and (events_date is None or firmographic_date[0] > events_date[0])
    )

    if use_firmographic:
        facts["funding_stage"] = firmographic_stage
        facts["last_round_date"] = firmographic_date[1]
        # That provider reports a stage and a date, not a round size. Carrying
        # the older round's amount against this newer date would be a fabricated
        # fact; null is the honest answer.
        facts["last_round_usd"] = None
    elif financing:
        facts["funding_stage"] = (
            _text(financing.get("financing_type_normalized"))
            or _text(financing.get("financing_type"))
            or firmographic_stage
        )
        facts["last_round_date"] = events_date[1] if events_date else None
        facts["last_round_usd"] = _number(financing.get("amount_normalized")) or _number(financing.get("amount"))
    else:
        facts["funding_stage"] = firmographic_stage
        facts["last_round_date"] = None
        facts["last_round_usd"] = None

    # --- jobs (node 13, reconciled against the careers page) --------------
    #
    # A zero from the jobs provider is not the same as "this company is not
    # hiring". On akuvo.com the provider returned no postings at all while the
    # company's own /careers page invited candidates to explore open positions —
    # and `open_eng_roles_count: 0` reads to stage_maturity as "mature steady
    # state without acute pressure", which is level 3. Levels 7 and 10 both
    # require a documented capacity gap, so a coverage hole in one provider
    # silently caps the component.
    #
    # When the provider found nothing but the careers page says otherwise, the
    # honest answer is null — we do not know — not zero. Null makes the
    # classifier say so and name the missing input; zero makes it assert
    # something false with confidence.
    jobs_ran = not _blank(context.get_input("jobs_domain"))
    open_eng, open_60d, senior = _summarize_jobs(
        _list(context.get_input("jobs")), today, jobs_ran,
    )
    careers_contradicts = (
        context.get_input("careers_lists_openings") == "yes" and open_eng == 0
    )
    if careers_contradicts:
        open_eng = open_60d = senior = None
    facts["open_eng_roles_count"] = open_eng
    facts["eng_roles_open_60d_plus"] = open_60d
    facts["senior_eng_roles"] = senior

    # --- news (node 14) ----------------------------------------------------
    # `[]` is evidence (we looked, the window is empty) where null is not
    # (we never looked) — and activation_state is told to read them
    # differently. The provider echoes the domain on every result including a
    # clean no-data one, so that is the ran-signal rather than the event list.
    news_ran = not _blank(context.get_input("news_domain"))
    facts["news_last_12mo"] = (
        _news_within_12_months(_list(context.get_input("news_events")), today) if news_ran else None
    )

    facts["captured_at"] = _now_iso()

    # Key order is the schema's, so a diff of two rows lines up.
    ordered = {key: facts.get(key) for key in FACT_KEYS}

    return {
        "facts": ordered,
        # The classifier prompts interpolate a string, not an object — an agent
        # prompt has no way to render a nested dict faithfully.
        "facts_json": json.dumps(ordered, ensure_ascii=False, indent=2, sort_keys=False),
        # Set when the two revenue providers landed two or more bands apart.
        # Node 24 reads it and forces revenue_range to low confidence, so the
        # downgrade is a rule rather than something the prompt asks for.
        "revenue_conflict": facts_conflict,
        # True when the jobs provider found nothing but the company's own
        # careers page advertises openings, so the three job counts were set to
        # null rather than zero.
        "jobs_coverage_gap": careers_contradicts,
        # Read by the scoring node. These three are the only facts the rubric
        # itself reads (tier-2 detection); everything else reaches it through a
        # classifier.
        "revenue_usd": ordered["revenue_estimate_usd"],
        "headcount_total": ordered["li_headcount"],
        "headcount_eng": ordered["eng_headcount_estimate"],
    }
