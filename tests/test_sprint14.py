import importlib
import unittest
from datetime import date, timedelta

from scripts.generate_dashboard import (
    _render_metadata,
    _render_priority_sections,
    enrich_dashboard_record,
    filter_dashboard_records,
    recommended_next_steps,
    sort_dashboard_records,
)
from scripts.job_importer import parse_imported_job
from scripts.job_source_registry import classify_source, normalize_job_source


TODAY = date(2026, 6, 30)


class SourceRegistryTests(unittest.TestCase):
    def test_employer_ats_sources(self):
        cases = (
            "https://company.wd5.myworkdayjobs.com/en-US/jobs/job/123",
            "https://boards.greenhouse.io/company/jobs/123",
            "https://jobs.lever.co/company/123",
            "https://jobs.ashbyhq.com/company/123",
            "https://jobs.smartrecruiters.com/Company/123",
            "https://company.icims.com/jobs/123/job",
            "https://company.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/job/123",
        )
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(classify_source(url)["source_type"], "Employer ATS")

    def test_industry_and_discovery_sources(self):
        cases = (
            ("https://www.entertainmentcareers.net/job/123", "Entertainment Job Board"),
            ("https://www.showbizjobs.com/jobs/123", "Entertainment Job Board"),
            ("https://www.musicbusinessworldwide.com/jobs/123", "Music Industry Job Board"),
            ("https://jobsbyrostr.com/jobs/123", "Music Industry Job Board"),
            ("https://careerhound.io/jobs/123", "Direct Company Discovery"),
            ("https://getwork.com/details/123", "Direct Company Discovery"),
            ("https://musiccareers.co/job/123", "Music Industry Job Board"),
            ("https://doorsopen.co/job/123", "Music Industry Job Board"),
            ("https://mediabistro.com/jobs/123", "Entertainment Job Board"),
            ("https://www.builtin.com/job/123", "Startup / Tech Job Board"),
            ("https://wellfound.com/jobs/123", "Startup / Tech Job Board"),
            ("https://workatastartup.com/jobs/123", "Startup / Tech Job Board"),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(classify_source(url)["source_type"], expected)

    def test_aggregator_and_gated_sources(self):
        jobgether = classify_source("https://jobgether.com/offer/123")
        self.assertEqual(jobgether["source_type"], "Remote Job Aggregator")
        self.assertEqual(jobgether["default_trust_label"], "Aggregator - Verify First")
        self.assertTrue(jobgether["requires_verification"])
        self.assertEqual(
            classify_source("https://jobtogether.com/jobs/123")["source_type"],
            "Remote Job Aggregator",
        )
        flexjobs = classify_source("https://flexjobs.com/jobs/123")
        self.assertEqual(flexjobs["source_type"], "Gated Source")
        self.assertTrue(flexjobs["gated"])
        self.assertEqual(
            classify_source("https://theladders.com/job/123")["source_type"],
            "Compensation-Focused Aggregator",
        )

    def test_unknown_domain_falls_back_safely(self):
        source = classify_source("https://unknown.example/jobs/123")
        self.assertEqual(source["source_type"], "Unknown Source")
        self.assertEqual(source["default_trust_label"], "Unknown Source")


class SourceNormalizationTests(unittest.TestCase):
    def test_employer_ats_url_is_canonical(self):
        url = "https://jobs.lever.co/company/abc"
        result = normalize_job_source({"official_url": url, "posting_date": "2026-06-25"}, TODAY)
        self.assertEqual(result["canonical_apply_url"], url)
        self.assertEqual(result["verification_status"], "Employer Source")
        self.assertEqual(result["freshness_risk"], "Low")

    def test_aggregator_with_employer_apply_url_is_verified(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobgether.com/offer/abc",
                "apply_url": "https://jobs.lever.co/company/abc",
                "posting_date": "2026-06-20",
            },
            TODAY,
        )
        self.assertEqual(result["canonical_apply_url"], "https://jobs.lever.co/company/abc")
        self.assertEqual(result["verification_status"], "Verified Active")

    def test_aggregator_content_can_supply_canonical_url(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobgether.com/offer/abc",
                "job_description": "Apply on the employer site: https://company.example/careers/abc",
                "posting_date": "2026-06-20",
            },
            TODAY,
        )
        self.assertEqual(result["canonical_apply_url"], "https://company.example/careers/abc")
        self.assertEqual(result["verification_status"], "Possibly Active")

    def test_aggregator_without_employer_url_requires_verification(self):
        result = normalize_job_source(
            {"official_url": "https://jobgether.com/offer/abc", "posting_date": "2026-06-20"},
            TODAY,
        )
        self.assertEqual(result["verification_status"], "Aggregator Only")
        self.assertEqual(result["source_trust_label"], "Aggregator - Verify First")
        self.assertIn("Open the original posting", result["recommended_next_step"])

    def test_missing_source_url_returns_safe_fallbacks(self):
        result = normalize_job_source({}, TODAY)
        self.assertEqual(result["source_name"], "Unknown")
        self.assertEqual(result["source_type"], "Unknown Source")
        self.assertEqual(result["verification_status"], "Not Verified")
        self.assertEqual(result["freshness_risk"], "Unknown")
        self.assertIn("source URL is missing", result["verification_notes"])
        self.assertIn("posting date unavailable", result["verification_notes"])

    def test_freshness_risk_boundaries(self):
        cases = ((0, "Low"), (14, "Low"), (15, "Medium"), (30, "Medium"), (31, "High"))
        for age, expected in cases:
            with self.subTest(age=age):
                result = normalize_job_source(
                    {
                        "official_url": "https://jobs.lever.co/company/abc",
                        "posting_date": (TODAY - timedelta(days=age)).isoformat(),
                    },
                    TODAY,
                )
                self.assertEqual(result["freshness_risk"], expected)

    def test_closed_language_overrides_source_quality(self):
        result = normalize_job_source(
            {
                "official_url": "https://jobs.lever.co/company/abc",
                "posting_date": "2026-06-25",
                "job_description": "This role is no longer accepting applications.",
            },
            TODAY,
        )
        self.assertEqual(result["verification_status"], "Stale / Closed Risk")
        self.assertEqual(result["source_trust_label"], "Stale Risk")

    def test_import_parser_adds_verification_without_extra_command(self):
        raw = """# Marketing Operations Director

Company: Example Co
Posting date: 2026-06-20

## Job Description

Lead marketing operations, improve campaign systems, partner cross-functionally, and build durable reporting workflows for a growing team.
"""
        result = parse_imported_job(raw, "https://jobs.ashbyhq.com/example/123")
        self.assertEqual(result["source_type"], "Employer ATS")
        self.assertEqual(result["canonical_apply_url"], "https://jobs.ashbyhq.com/example/123")


class SourceDashboardTests(unittest.TestCase):
    def _record(self, identifier, **updates):
        record = {
            "id": identifier,
            "company": identifier.title(),
            "role": "Director, Operations",
            "status": "Drafted",
            "show_on_dashboard": True,
            "match_score": 80,
            "match_tier": "Good Match",
            "recommended_action": "Generate Package",
            "source_name": "Jobgether",
            "source_type": "Remote Job Aggregator",
            "source_trust_label": "Aggregator - Verify First",
            "verification_status": "Aggregator Only",
            "freshness_risk": "Low",
        }
        record.update(updates)
        return record

    def test_source_filters(self):
        direct = self._record(
            "direct", source_type="Employer ATS", source_trust_label="Verified Company Source",
            verification_status="Employer Source",
        )
        aggregator = self._record("aggregator")
        records = [direct, aggregator]
        self.assertEqual(filter_dashboard_records(records, source_type="Employer ATS"), [direct])
        self.assertEqual(filter_dashboard_records(records, verification_status="Aggregator Only"), [aggregator])
        self.assertEqual(filter_dashboard_records(records, trust_label="Verified Company Source"), [direct])

    def test_verification_sort_puts_direct_above_aggregator_and_stale(self):
        records = [
            self._record("stale", source_trust_label="Stale Risk", verification_status="Stale / Closed Risk"),
            self._record("aggregator"),
            self._record("direct", source_trust_label="Direct Employer", verification_status="Employer Source"),
        ]
        result = sort_dashboard_records(records, "Verification Quality: Best to Worst")
        self.assertEqual([item["id"] for item in result], ["direct", "aggregator", "stale"])

    def test_verify_first_guidance_for_aggregator(self):
        step = recommended_next_steps([self._record("aggregator")], "Apply Mode")[0]
        self.assertIn("Open original posting", step)

    def test_apply_guidance_prioritizes_verified_source(self):
        aggregator = self._record("aggregator", match_score=95)
        direct = self._record(
            "direct", match_score=80, source_trust_label="Verified Company Source",
            verification_status="Employer Source",
        )
        steps = recommended_next_steps([aggregator, direct], "Apply Mode")
        self.assertIn("Direct", steps[0])

    def test_dashboard_metadata_has_source_verification_fields(self):
        record = self._record("display", canonical_apply_url="https://jobs.lever.co/example/123")
        content = _render_metadata({"tracker": record})
        for label in ("Source Type", "Trust Label", "Verification Status", "Canonical Apply URL", "Freshness Risk"):
            self.assertIn(label, content)

    def test_streamlit_metadata_has_source_verification_fields(self):
        app = importlib.import_module("app")
        content = app._metadata_html(self._record("streamlit"), {})
        for label in ("Source Type", "Trust Label", "Verification Status", "Freshness Risk"):
            self.assertIn(label, content)

    def test_html_dashboard_has_source_verification_sections(self):
        record = self._record("aggregator")
        package = {"company": record["company"], "role": record["role"], "tracker": record, "files": {}}
        content = _render_priority_sections({"active": [], "draft": [package], "hidden": []})
        for heading in (
            "Verified / Employer Source Roles", "Industry Board Roles", "Aggregator - Verify First",
            "Gated / Limited Visibility", "Unknown / Cannot Verify", "Stale or Closed Risk",
        ):
            self.assertIn(heading, content)

    def test_old_record_enrichment_has_safe_fallbacks(self):
        record = enrich_dashboard_record({"id": "legacy", "company": "Legacy", "role": "Role"}, TODAY)
        self.assertEqual(record["source_name"], "Unknown")
        self.assertEqual(record["source_type"], "Unknown Source")
        self.assertEqual(record["verification_status"], "Not Verified")
        self.assertEqual(record["freshness_risk"], "Unknown")


if __name__ == "__main__":
    unittest.main()
