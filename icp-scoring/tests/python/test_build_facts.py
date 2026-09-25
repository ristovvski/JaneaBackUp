"""Unit tests for clay/code/15_build_facts.py — the node that decides what the
classifiers see.

This node is where "we did not look" becomes null, "we looked and found
nothing" becomes 0 or [], a revenue band becomes a number, and two disagreeing
funding sources become one coherent round. Every one of those is a decision the
rubric depends on, and none of it was covered before.

Run through tests/contract/facts_node.test.mjs so `npm test` carries it.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SOURCE = os.path.join(ROOT, "clay", "code", "15_build_facts.py")

# Load the node exactly as it is written. Not a copy: a copy drifts.
NODE = {}
with open(SOURCE, "r", encoding="utf-8") as handle:
    exec(compile(handle.read(), SOURCE, "exec"), NODE)


class FakeContext(dict):
    """Stands in for Clay's context, which is a dict with get_input()."""

    def get_input(self, key):
        return self.get(key)


def run(**inputs):
    return NODE["handler"](FakeContext(inputs))


class RevenueBands(unittest.TestCase):
    def test_a_band_becomes_its_midpoint(self):
        out = run(pdl_revenue="$50M-$100M", request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 75_000_000)

    def test_the_raw_band_survives_in_revenue_source(self):
        out = run(pdl_revenue="$50M-$100M", request_id="r", org_id="1")
        self.assertIn("$50M-$100M", out["facts"]["revenue_source"])

    def test_a_scalar_is_left_alone(self):
        out = run(pdl_revenue=42_000_000, request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 42_000_000)
        self.assertNotIn("band", out["facts"]["revenue_source"])

    def test_unparseable_revenue_is_null_not_zero(self):
        # The whole point. "unknown" must never reach the classifier as 0,
        # which it would read as pre-revenue.
        out = run(pdl_revenue="unknown", request_id="r", org_id="1")
        self.assertIsNone(out["facts"]["revenue_estimate_usd"])
        self.assertIsNone(out["facts"]["revenue_source"])

    def test_a_disagreement_names_both_providers_in_the_source_line(self):
        # Whatever the rule does with the number, both providers and both bands
        # stay visible: the classifiers are told to cite `revenue_source`, and a
        # reviewer six months on needs to see what the figure rested on.
        # The >=2-band behaviour itself is covered in RevenueBandConflict.
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="10M-25M",
                  request_id="r", org_id="1")
        source = out["facts"]["revenue_source"]
        self.assertIn("10M-25M", source)
        self.assertIn("$50M-$100M", source)

    def test_agreeing_sources_are_not_flagged(self):
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="60M-90M",
                  request_id="r", org_id="1")
        self.assertNotIn("disagrees", out["facts"]["revenue_source"])

    def test_profile_is_the_fallback_when_the_firmographic_provider_is_silent(self):
        out = run(profile_annual_revenue="10M-25M", request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 17_500_000)
        self.assertIn("Company profile lookup", out["facts"]["revenue_source"])


class RevenueBandConflict(unittest.TestCase):
    """The rule: one band apart is noise, two or more is a conflict.

    On a conflict the LOWER figure wins, regardless of which provider is
    primary, and `revenue_conflict` goes downstream so node 24 can force the
    confidence down in code rather than asking the prompt nicely.
    """

    def test_the_akuvo_case_takes_the_lower_band(self):
        # The case this rule was written for: $50M-$100M against 10M-25M on a
        # 90-person company founded in 2019 that has raised $13M.
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="10M-25M",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 17_500_000)
        self.assertTrue(out["revenue_conflict"])
        self.assertIn("CONFLICT", out["facts"]["revenue_source"])
        self.assertIn("2 bands apart", out["facts"]["revenue_source"])

    def test_the_lower_figure_wins_even_when_the_primary_is_lower(self):
        # Not "prefer the secondary" — prefer the LOWER. Direction must not
        # depend on which provider happened to be primary.
        out = run(pdl_revenue="$1M-$10M", profile_annual_revenue="$250M-$500M",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 5_500_000)
        self.assertTrue(out["revenue_conflict"])

    def test_one_band_apart_keeps_the_primary_and_is_not_a_conflict(self):
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="$25M-$50M",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 75_000_000)
        self.assertFalse(out["revenue_conflict"])
        self.assertIn("disagrees by one band", out["facts"]["revenue_source"])

    def test_the_microsoft_case_is_not_a_conflict(self):
        # $10B+ against 100B-1T is one band apart at the top of the ladder.
        out = run(pdl_revenue="$10B+", profile_annual_revenue="100B-1T",
                  request_id="r", org_id="1")
        self.assertFalse(out["revenue_conflict"])
        self.assertEqual(out["facts"]["revenue_estimate_usd"], 10_000_000_000)

    def test_agreement_is_never_a_conflict(self):
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="60M-90M",
                  request_id="r", org_id="1")
        self.assertFalse(out["revenue_conflict"])
        self.assertNotIn("CONFLICT", out["facts"]["revenue_source"])

    def test_one_provider_alone_is_never_a_conflict(self):
        for kwargs in ({"pdl_revenue": "$50M-$100M"}, {"profile_annual_revenue": "10M-25M"}):
            out = run(request_id="r", org_id="1", **kwargs)
            self.assertFalse(out["revenue_conflict"], kwargs)

    def test_the_band_ladder_is_scale_invariant(self):
        # "Two bands apart" must mean the same thing at $10M and at $10B —
        # which is the whole reason for a ladder instead of a ratio.
        idx = NODE["_band_index"]
        self.assertEqual(idx(17_500_000) - idx(5_000_000), 1)      # 10-25M vs 1-10M
        self.assertEqual(idx(75_000_000) - idx(17_500_000), 2)     # 50-100M vs 10-25M
        self.assertEqual(idx(5e10) - idx(5e9), 1)                  # 10-100B vs 1-10B
        self.assertIsNone(idx(None))

    def test_a_conflict_still_produces_a_number_the_scorer_can_use(self):
        out = run(pdl_revenue="$50M-$100M", profile_annual_revenue="10M-25M",
                  request_id="r", org_id="1")
        self.assertEqual(out["revenue_usd"], out["facts"]["revenue_estimate_usd"])
        self.assertIsInstance(out["facts"]["revenue_estimate_usd"], float)


class Funding(unittest.TestCase):
    EVENTS = [{"effective_date": "2023-04-12", "financing_type_normalized": None,
               "amount_normalized": 10_000_000}]

    def test_the_newer_round_wins_and_carries_its_own_stage(self):
        out = run(financing_events=self.EVENTS,
                  pdl_funding_stage="private_equity", pdl_last_funding_date="2025-09-18",
                  request_id="r", org_id="1")
        facts = out["facts"]
        self.assertEqual(facts["last_round_date"], "2025-09-18")
        self.assertEqual(facts["funding_stage"], "private_equity")
        # The amount belongs to the 2023 round, not this one.
        self.assertIsNone(facts["last_round_usd"])

    def test_the_events_provider_wins_when_it_is_newer_and_keeps_its_amount(self):
        out = run(financing_events=[{"effective_date": "2026-01-05",
                                     "financing_type_normalized": "series_b",
                                     "amount_normalized": 30_000_000}],
                  pdl_funding_stage="seed", pdl_last_funding_date="2024-01-01",
                  request_id="r", org_id="1")
        facts = out["facts"]
        self.assertEqual(facts["last_round_date"], "2026-01-05")
        self.assertEqual(facts["funding_stage"], "series_b")
        self.assertEqual(facts["last_round_usd"], 30_000_000)

    def test_a_stage_is_never_borrowed_across_a_date(self):
        # The bug this was written for: stage from one round, date from another.
        out = run(financing_events=self.EVENTS,
                  pdl_funding_stage="private_equity", pdl_last_funding_date="2025-09-18",
                  request_id="r", org_id="1")
        self.assertNotEqual(
            (out["facts"]["funding_stage"], out["facts"]["last_round_date"]),
            ("private_equity", "2023-04-12"),
        )

    def test_no_funding_data_at_all_is_null_throughout(self):
        out = run(request_id="r", org_id="1")
        for key in ("funding_stage", "last_round_date", "last_round_usd"):
            self.assertIsNone(out["facts"][key], key)


class LookedVersusNotLooked(unittest.TestCase):
    def test_jobs_never_asked_is_null(self):
        out = run(request_id="r", org_id="1")
        for key in ("open_eng_roles_count", "eng_roles_open_60d_plus", "senior_eng_roles"):
            self.assertIsNone(out["facts"][key], key)

    def test_jobs_asked_and_empty_is_zero(self):
        out = run(jobs=[], jobs_domain="akuvo.com", request_id="r", org_id="1")
        self.assertEqual(out["facts"]["open_eng_roles_count"], 0)
        self.assertEqual(out["facts"]["eng_roles_open_60d_plus"], 0)
        self.assertEqual(out["facts"]["senior_eng_roles"], 0)

    def test_news_never_asked_is_null_and_asked_but_empty_is_a_list(self):
        self.assertIsNone(run(request_id="r", org_id="1")["facts"]["news_last_12mo"])
        out = run(news_events=[], news_domain="akuvo.com", request_id="r", org_id="1")
        self.assertEqual(out["facts"]["news_last_12mo"], [])

    def test_an_engineering_role_is_recognised_and_a_sales_one_is_not(self):
        out = run(jobs_domain="x.com", request_id="r", org_id="1", jobs=[
            {"title": "Staff Software Engineer", "categories": ["engineering"],
             "first_seen_at": "2020-01-01", "seniority": "staff"},
            {"title": "Account Executive", "categories": ["sales"],
             "first_seen_at": "2020-01-01"},
        ])
        self.assertEqual(out["facts"]["open_eng_roles_count"], 1)
        self.assertEqual(out["facts"]["senior_eng_roles"], 1)
        self.assertEqual(out["facts"]["eng_roles_open_60d_plus"], 1)

    def test_a_role_opened_today_is_not_counted_as_open_sixty_days(self):
        today = NODE["_now_iso"]()[:10]
        out = run(jobs_domain="x.com", request_id="r", org_id="1", jobs=[
            {"title": "Backend Engineer", "categories": ["engineering"], "first_seen_at": today},
        ])
        self.assertEqual(out["facts"]["open_eng_roles_count"], 1)
        self.assertEqual(out["facts"]["eng_roles_open_60d_plus"], 0)


class JobsCoverageGap(unittest.TestCase):
    """A provider's silence must not become an assertive zero.

    This is the Akuvo stage_maturity case: the jobs provider knew the domain and
    returned no postings, while the company's own /careers page invited
    applications. Zero reads as "no capacity pressure", which caps
    stage_maturity at 3; null reads as "we do not know", which is the truth.
    """

    def test_provider_zero_against_a_hiring_careers_page_becomes_null(self):
        out = run(jobs=[], jobs_domain="akuvo.com", careers_lists_openings="yes",
                  request_id="r", org_id="1")
        for key in ("open_eng_roles_count", "eng_roles_open_60d_plus", "senior_eng_roles"):
            self.assertIsNone(out["facts"][key], key)
        self.assertTrue(out["jobs_coverage_gap"])

    def test_provider_zero_with_a_careers_page_saying_no_stays_zero(self):
        out = run(jobs=[], jobs_domain="akuvo.com", careers_lists_openings="no",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["open_eng_roles_count"], 0)
        self.assertFalse(out["jobs_coverage_gap"])

    def test_an_unreachable_careers_page_does_not_override_the_provider(self):
        # "unknown" is not evidence of hiring. Only a positive signal from the
        # page overrides the provider.
        out = run(jobs=[], jobs_domain="akuvo.com", careers_lists_openings="unknown",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["open_eng_roles_count"], 0)
        self.assertFalse(out["jobs_coverage_gap"])

    def test_real_postings_are_never_overridden(self):
        out = run(jobs_domain="x.com", careers_lists_openings="yes",
                  request_id="r", org_id="1", jobs=[
                      {"title": "Senior Backend Engineer", "categories": ["engineering"],
                       "first_seen_at": "2020-01-01", "seniority": "senior"},
                  ])
        self.assertEqual(out["facts"]["open_eng_roles_count"], 1)
        self.assertFalse(out["jobs_coverage_gap"])

    def test_a_provider_that_never_ran_is_still_null_not_a_coverage_gap(self):
        out = run(careers_lists_openings="yes", request_id="r", org_id="1")
        self.assertIsNone(out["facts"]["open_eng_roles_count"])
        self.assertFalse(out["jobs_coverage_gap"])


class NewsWindow(unittest.TestCase):
    def test_an_undated_item_is_dropped(self):
        out = run(news_domain="x.com", request_id="r", org_id="1", news_events=[
            {"summary": "Something happened"},
        ])
        self.assertEqual(out["facts"]["news_last_12mo"], [])

    def test_an_item_older_than_the_window_is_dropped(self):
        out = run(news_domain="x.com", request_id="r", org_id="1", news_events=[
            {"effective_date": "2001-01-01", "summary": "Ancient"},
        ])
        self.assertEqual(out["facts"]["news_last_12mo"], [])

    def test_a_recent_item_is_kept_with_its_date(self):
        today = NODE["_now_iso"]()[:10]
        out = run(news_domain="x.com", request_id="r", org_id="1", news_events=[
            {"effective_date": today, "summary": "Launched a thing", "category": "launches"},
        ])
        items = out["facts"]["news_last_12mo"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date"], today)
        self.assertEqual(items[0]["headline"], "Launched a thing")


class Shape(unittest.TestCase):
    REQUIRED = [
        "request_id", "org_id", "deal_id", "identifier_kind", "identifier_value",
        "domain", "linkedin_url", "company_name", "hq_country", "hq_state",
        "li_headcount", "li_industry", "li_description", "li_founded", "li_hq",
        "website_summary", "revenue_estimate_usd", "revenue_source",
        "funding_stage", "last_round_date", "last_round_usd",
        "open_eng_roles_count", "eng_roles_open_60d_plus", "senior_eng_roles",
        "eng_headcount_estimate", "news_last_12mo",
    ]

    def test_every_schema_key_is_present_even_with_no_enrichment_at_all(self):
        facts = run(request_id="r", org_id="1", identifier_kind="name",
                    identifier_value="x", company_name="X")["facts"]
        for key in self.REQUIRED:
            self.assertIn(key, facts, key)

    def test_facts_json_parses_and_matches_the_facts_object(self):
        out = run(request_id="r", org_id="1")
        self.assertEqual(json.loads(out["facts_json"]), out["facts"])

    def test_the_three_scoring_facts_are_surfaced_for_the_scorer(self):
        out = run(pdl_revenue=1000, profile_employee_count=10, pdl_eng_headcount=4,
                  request_id="r", org_id="1")
        self.assertEqual(out["revenue_usd"], 1000)
        self.assertEqual(out["headcount_total"], 10)
        self.assertEqual(out["headcount_eng"], 4)

    def test_a_pipedrive_domain_is_never_overwritten_by_a_provider(self):
        out = run(domain="acme.com", domain_for_enrichment="provider-guess.com",
                  request_id="r", org_id="1")
        self.assertEqual(out["facts"]["domain"], "acme.com")


class DateArithmetic(unittest.TestCase):
    def test_days_from_civil_matches_a_known_set_of_epochs(self):
        dfc = NODE["_days_from_civil"]
        self.assertEqual(dfc(1970, 1, 1), 0)
        self.assertEqual(dfc(1970, 1, 2), 1)
        self.assertEqual(dfc(1969, 12, 31), -1)
        self.assertEqual(dfc(2000, 3, 1), 11017)     # past a leap-century boundary
        self.assertEqual(dfc(2024, 2, 29), 19782)    # a real leap day

    def test_a_non_date_is_rejected_rather_than_guessed(self):
        for bad in (None, "", "not-a-date", "2026", "20260101", 12345):
            self.assertIsNone(NODE["_date"](bad), repr(bad))


if __name__ == "__main__":
    unittest.main(verbosity=2)
