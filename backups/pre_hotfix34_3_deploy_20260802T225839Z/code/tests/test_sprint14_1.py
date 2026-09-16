import unittest
from datetime import date

import app
from scripts.generate_dashboard import (
    _render_metadata,
    enrich_dashboard_record,
    recommended_next_steps,
    source_verification_caution,
)
from scripts.job_freshness import detect_job_freshness
from scripts.job_importer import parse_imported_job
from scripts.job_source_registry import classify_source, normalize_job_source
from scripts.parse_job import extract_metadata
from scripts.score_match import score_job_data


TODAY = date(2026, 6, 30)


class LegacyEmployerFallbackTests(unittest.TestCase):
    def test_clear_employer_labels_without_urls_remain_trusted(self):
        for company, source in (
            ("Paramount", "Official Paramount Careers"),
            ("Google", "Google Careers"),
            ("Sony", "Sony Careers"),
        ):
            with self.subTest(source=source):
                result = normalize_job_source({"company": company, "source": source}, TODAY)
                self.assertEqual(result["source_type"], "Direct Employer")
                self.assertEqual(result["source_trust_label"], "Direct Employer")
                self.assertEqual(result["verification_status"], "Employer Source")
                self.assertEqual(result["source_confidence"], "Medium")
                self.assertEqual(result["freshness_risk"], "Unknown")
                self.assertIn("original source URL was not stored", result["verification_notes"])
                self.assertNotIn("No registry match", result["verification_notes"])

    def test_unknown_missing_url_remains_unknown(self):
        result = normalize_job_source({"source": "A friend sent this"}, TODAY)
        self.assertEqual(result["source_type"], "Unknown Source")
        self.assertEqual(result["verification_status"], "Not Verified")

    def test_employer_fallback_suppresses_harsh_banner(self):
        result = normalize_job_source(
            {"company": "Paramount", "source": "Official Paramount Careers"}, TODAY
        )
        self.assertEqual(source_verification_caution(result), "")

    def test_unverifiable_sources_keep_harsh_banner(self):
        aggregator = {
            "source_type": "Remote Job Aggregator",
            "source_trust_label": "Aggregator - Verify First",
            "verification_status": "Aggregator Only",
        }
        unknown = {
            "source_type": "Unknown Source",
            "source_trust_label": "Cannot Verify",
            "verification_status": "Cannot Verify",
        }
        self.assertIn("Verify on the employer site", source_verification_caution(aggregator))
        self.assertIn("Source not verified", source_verification_caution(unknown))


class DigitalHireTests(unittest.TestCase):
    def test_digitalhire_is_an_employer_ats(self):
        source = classify_source("https://jobs.digitalhire.com/aeg/123")
        self.assertEqual(source["display_name"], "DigitalHire")
        self.assertEqual(source["source_type"], "Employer ATS")
        self.assertTrue(source["requires_verification"])

    def test_digitalhire_preserves_employer_identity(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobs.digitalhire.com/aeg/123",
                "company": "AEG Worldwide / AXS",
                "job_description": "Posted 10 days ago.",
            },
            TODAY,
        )
        self.assertEqual(result["source_name"], "DigitalHire")
        self.assertEqual(result["source_type"], "Employer ATS")
        self.assertEqual(result["source_trust_label"], "Verified Company Source")
        self.assertEqual(result["verification_status"], "Employer Source")
        self.assertEqual(result["canonical_employer"], "AEG Worldwide / AXS")

    def test_import_parser_uses_specific_digitalhire_name(self):
        raw = """# Director, Marketing Operations

Company: AEG Worldwide / AXS

## Job Description

Lead marketing operations, campaign planning, workflow systems, reporting, and cross-functional delivery for live entertainment brands. Posted 10 days ago.
"""
        result = parse_imported_job(raw, "https://jobs.digitalhire.com/aeg/123")
        self.assertEqual(result["source"], "DigitalHire")
        self.assertEqual(result["source_name"], "DigitalHire")
        self.assertEqual(result["source_type"], "Employer ATS")


class ExplicitFreshnessTests(unittest.TestCase):
    def test_relative_day_risk_boundaries(self):
        for phrase, expected in (
            ("posted 10 days ago", "Low"),
            ("posted 20 days ago", "Medium"),
            ("posted 45 days ago", "High"),
        ):
            with self.subTest(phrase=phrase):
                result = normalize_job_source(
                    {
                        "official_url": "https://jobs.digitalhire.com/aeg/123",
                        "job_description": phrase,
                    },
                    TODAY,
                )
                self.assertEqual(result["freshness_risk"], expected)

    def test_three_month_age_is_stale_not_open(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobs.digitalhire.com/aeg/123",
                "job_description": "Posted 3 months ago.",
            },
            TODAY,
        )
        self.assertEqual(result["freshness_risk"], "High")
        self.assertEqual(result["freshness_label"], "Stale / Verify manually")
        self.assertEqual(result["posting_status"], "Stale / Closed Risk")
        self.assertEqual(result["verification_status"], "Stale / Closed Risk")

    def test_other_explicit_stale_age_phrases_are_detected(self):
        for phrase, minimum_age in (
            ("posted 100 days ago", 100),
            ("posted 30+ days ago", 30),
            ("posted more than 30 days ago", 31),
            ("older than 30 days", 31),
        ):
            with self.subTest(phrase=phrase):
                result = detect_job_freshness(phrase, TODAY)
                self.assertGreaterEqual(result["age_days"], minimum_age)

    def test_closed_language_overrides_source(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobs.digitalhire.com/aeg/123",
                "job_description": "This role is no longer accepting applications.",
            },
            TODAY,
        )
        self.assertEqual(result["verification_status"], "Stale / Closed Risk")

    def test_missing_date_is_unknown_and_not_automatically_open(self):
        result = detect_job_freshness("Lead business operations.", TODAY)
        self.assertEqual(result["category"], "Unknown freshness")
        self.assertEqual(result["posting_status"], "Verify manually")

    def test_explicit_stale_age_cannot_become_fresh(self):
        result = detect_job_freshness(
            "Posted 3 months ago. This is an exciting fast-moving opportunity.", TODAY
        )
        self.assertEqual(result["category"], "Stale")
        self.assertNotEqual(result["posting_status"], "Open")

    def test_stale_high_match_requires_review_first(self):
        report = score_job_data(
            {
                "job_title": "Director, Marketing Operations",
                "company": "AEG Worldwide / AXS",
                "location": "Los Angeles, CA hybrid",
                "salary_range": "$150,000-$180,000",
                "job_description": (
                    "Posted 3 months ago. Lead strategic marketing operations, campaign operations, "
                    "workflow automation, process improvement, media operations, and cross-functional "
                    "planning for a global live entertainment company."
                ),
            }
        )
        self.assertNotEqual(report["recommended_action"], "Generate Package")
        self.assertTrue(any("stale" in gap.lower() for gap in report["match_gaps"]))


class SalaryGuardrailTests(unittest.TestCase):
    def test_budget_and_revenue_figures_are_not_salary(self):
        for text in (
            "$5M annual budget",
            "revenue growth from a $5M+ annual budget",
            "paid media budget of $5 million",
        ):
            with self.subTest(text=text):
                self.assertIsNone(extract_metadata(text)["salary_range"])

    def test_true_compensation_formats_still_parse(self):
        for text, expected in (
            ("$130,000-$180,000 USD", "$130,000-$180,000 USD"),
            ("$85k to $100k annually", "$85k to $100k annually"),
            ("$65/hour", "$65/hour"),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_metadata(text)["salary_range"], expected)


class DashboardAndImportWarningTests(unittest.TestCase):
    def _stale_digitalhire(self):
        return normalize_job_source(
            {
                "official_url": "https://jobs.digitalhire.com/aeg/123",
                "company": "AEG Worldwide / AXS",
                "job_description": "Posted 3 months ago. Manage a $5M annual budget.",
            },
            TODAY,
        )

    def test_dashboard_shows_corrected_source_freshness_and_salary(self):
        tracker = {
            **self._stale_digitalhire(),
            "salary_range": "Not disclosed",
        }
        content = _render_metadata({"tracker": tracker})
        for value in (
            "DigitalHire", "Employer ATS", "Verified Company Source", "Stale / Closed Risk",
            "High", "Not disclosed",
        ):
            self.assertIn(value, content)
        self.assertNotIn("<dd>$5</dd>", content)

    def test_legacy_missing_date_does_not_keep_optimistic_open_status(self):
        record = enrich_dashboard_record(
            {
                "company": "Paramount",
                "role": "Director, Marketing Operations",
                "source": "Official Paramount Careers",
                "posting_date": "",
                "posting_status": "Open",
            },
            TODAY,
        )
        self.assertEqual(record["posting_status"], "Verify manually")

    def test_dashboard_stale_warning_and_next_step_are_visible(self):
        tracker = {
            **self._stale_digitalhire(),
            "company": "AEG Worldwide / AXS",
            "role": "Director, Marketing Operations",
            "match_score": 90,
            "match_tier": "Strong Match",
            "recommended_action": "Review First",
        }
        self.assertIn("verify it is active", source_verification_caution(tracker))
        self.assertIn("verify", recommended_next_steps([tracker], "Apply Mode")[0].lower())

    def test_import_preview_warnings_cover_stale_ats_and_budget(self):
        intelligence = app.detect_prospect_intelligence(
            {
                "official_url": "https://jobs.digitalhire.com/aeg/123",
                "company": "AEG Worldwide / AXS",
                "job_title": "Director, Marketing Operations",
                "job_description": "Posted 3 months ago. Manage a $5M annual budget.",
            }
        )
        messages = app.prospect_warning_messages(intelligence)
        self.assertTrue(any("stale" in message.lower() for message in messages))
        self.assertTrue(any("budget or spend" in message.lower() for message in messages))
        self.assertTrue(any("employer ATS" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
