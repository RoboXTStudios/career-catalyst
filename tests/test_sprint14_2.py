import tempfile
import unittest
from datetime import date
from pathlib import Path

import app
from scripts.application_tracker import load_application_tracker
from scripts.dynamic_role_intelligence import detect_role_family, get_effective_voice_profile
from scripts.generate_dashboard import (
    _render_metadata,
    _render_notes,
    enrich_dashboard_record,
    recommended_next_steps,
    source_verification_caution,
)
from scripts.job_importer import parse_imported_job
from scripts.job_source_registry import classify_source, normalize_job_source
from scripts.parse_job import extract_metadata
from scripts.prospect_intake import create_prospect


TODAY = date(2026, 6, 30)
GAMEJOBS_URL = "https://gamejobs.co/Operations-Director-at-teamLFG"
GREENHOUSE_URL = "https://job-boards.greenhouse.io/teamlfg/jobs/6101992004"


class Sprint142SourceClassificationTests(unittest.TestCase):
    def test_gamejobs_is_gaming_industry_board_not_direct_employer(self):
        classified = classify_source(GAMEJOBS_URL)
        self.assertEqual(classified["display_name"], "GameJobs.co")
        self.assertEqual(classified["source_type"], "Gaming Industry Job Board")
        self.assertEqual(classified["default_trust_label"], "Industry Job Board")
        self.assertTrue(classified["requires_verification"])

        normalized = normalize_job_source(
            {
                "official_url": GAMEJOBS_URL,
                "company": "teamLFG",
                "source": "Company career page",
                "job_description": "Posted 20 hours ago.",
            },
            TODAY,
        )
        self.assertEqual(normalized["source_name"], "GameJobs.co")
        self.assertNotEqual(normalized["source_type"], "Direct Employer")
        self.assertEqual(normalized["verification_status"], "Industry Board")
        self.assertIn("Open the original posting", normalized["recommended_next_step"])

    def test_greenhouse_preserves_employer_ats_identity(self):
        normalized = normalize_job_source(
            {"official_url": GREENHOUSE_URL, "company": "teamLFG"},
            TODAY,
        )
        self.assertEqual(normalized["source_name"], "Greenhouse")
        self.assertEqual(normalized["source_type"], "Employer ATS")
        self.assertEqual(normalized["verification_status"], "Employer Source")
        self.assertNotEqual(normalized["source_name"], "Company career page")

    def test_unknown_external_board_does_not_become_direct_employer_from_generic_label(self):
        normalized = normalize_job_source(
            {
                "official_url": "https://externalboard.example/jobs/operations-director-teamlfg",
                "company": "teamLFG",
                "source": "Company career page",
            },
            TODAY,
        )
        self.assertEqual(normalized["source_type"], "Unknown Source")
        self.assertNotEqual(normalized["verification_status"], "Employer Source")
        self.assertEqual(normalized["source_name"], "externalboard.example")

    def test_employer_domain_and_known_ats_can_be_trusted(self):
        direct = normalize_job_source(
            {
                "official_url": "https://teamlfg.com/careers/operations-director",
                "company": "teamLFG",
            },
            TODAY,
        )
        self.assertEqual(direct["source_type"], "Direct Employer")
        self.assertEqual(direct["verification_status"], "Employer Source")

        ats = normalize_job_source(
            {"official_url": "https://jobs.ashbyhq.com/teamlfg/123", "company": "teamLFG"},
            TODAY,
        )
        self.assertEqual(ats["source_name"], "Ashby")
        self.assertEqual(ats["source_type"], "Employer ATS")


class Sprint142FieldNormalizationTests(unittest.TestCase):
    def test_import_parser_cleans_title_company_location_and_work_arrangement(self):
        raw = """# Operations Director at teamLFG

Salary range: $204,000 - $307,000 USD

## Job Description

This hybrid role is based in Los Angeles, CA and leads business operations, studio operating rhythms, planning, process improvement, and cross-functional delivery for a growing game studio.
"""
        parsed = parse_imported_job(raw, GAMEJOBS_URL)
        self.assertEqual(parsed["job_title"], "Operations Director")
        self.assertEqual(parsed["company"], "teamLFG")
        self.assertEqual(parsed["location"], "Los Angeles, CA")
        self.assertEqual(parsed["work_arrangement"], "Hybrid")
        self.assertEqual(parsed["salary_range"], "$204,000 - $307,000 USD")

    def test_blank_location_defaults_to_not_specified(self):
        raw = """# Operations Director at teamLFG

## Job Description

Lead business operations, studio planning, operating cadence, reporting, and cross-functional delivery for a game studio with several partner teams and evolving production needs.
"""
        parsed = parse_imported_job(raw, GREENHOUSE_URL)
        self.assertEqual(parsed["location"], "Not specified")
        self.assertEqual(parsed["work_arrangement"], "Not specified")

    def test_salary_guardrails_from_sprint_14_1_still_hold(self):
        self.assertEqual(
            extract_metadata("$204,000 - $307,000 USD")["salary_range"],
            "$204,000 - $307,000 USD",
        )
        self.assertIsNone(extract_metadata("Manage a $5M annual production budget.")["salary_range"])


class Sprint142RoleFamilyTests(unittest.TestCase):
    def test_operations_director_in_gaming_context_stays_operations(self):
        role_family = detect_role_family(
            "Operations Director",
            "Gaming studio role leading operating cadence, business operations, planning, process improvement, and cross-functional execution.",
        )
        self.assertEqual(role_family, "business_operations")

    def test_product_strategy_ops_requires_product_strategy_evidence(self):
        role_family = detect_role_family(
            "Operations Director",
            "Own product roadmap planning, product lifecycle operations, feature prioritization, and product strategy rituals.",
        )
        self.assertEqual(role_family, "product_strategy_ops")

    def test_company_voice_does_not_overwrite_role_family(self):
        profile = get_effective_voice_profile(
            company_name="teamLFG",
            job_title="Operations Director",
            job_description="Gaming fandom company seeking a leader for business operations, planning, reporting, and cross-functional delivery.",
        )
        self.assertEqual(profile["company_category"], "gaming_fandom")
        self.assertEqual(profile["role_family"], "business_operations")


class Sprint142ActionAndPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        (self.root / "jobs").mkdir()
        (self.root / "data" / "application_tracker.yml").write_text(
            "applications: []\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_gamejobs_good_match_next_action_includes_verify_first_guidance(self):
        result = create_prospect(
            {
                "official_url": GAMEJOBS_URL,
                "company": "teamLFG",
                "job_title": "Operations Director",
                "location": "Remote",
                "work_arrangement": "Remote",
                "salary_range": "$204,000 - $307,000 USD",
                "job_description": (
                    "Posted 20 hours ago. Lead business operations, studio operations, operating cadence, "
                    "workflow systems, process improvement, executive reporting, planning, and cross-functional "
                    "delivery for a gaming company building creative technology and entertainment experiences."
                ),
            },
            self.root,
        )
        application = load_application_tracker(self.root)[0]
        self.assertEqual(result["application"]["source_name"], "GameJobs.co")
        self.assertEqual(application["verification_status"], "Industry Board")
        self.assertIn("Original posting should be confirmed", application["next_action"])
        self.assertEqual(application["role_family"], "business_operations")

    def test_aggregator_strong_match_leans_review_first_without_canonical_url(self):
        result = create_prospect(
            {
                "official_url": "https://ziprecruiter.com/jobs/teamlfg-operations-director",
                "company": "teamLFG",
                "job_title": "Operations Director",
                "location": "Remote",
                "work_arrangement": "Remote",
                "salary_range": "$204,000 - $307,000 USD",
                "job_description": (
                    "Lead strategic business operations, operational planning, workflow automation, executive "
                    "communication, process improvement, cross-functional delivery, and reporting for a gaming "
                    "technology company. Posted 2 days ago."
                ),
            },
            self.root,
        )
        application = result["application"]
        self.assertEqual(application["source_type"], "Generic Aggregator")
        self.assertEqual(application["recommended_action"], "Review First")
        self.assertIn("Original posting should be confirmed", application["next_action"])

    def test_add_prospect_preview_warnings_for_gamejobs_and_greenhouse_partial(self):
        gamejobs_intelligence = app.detect_prospect_intelligence(
            {
                "official_url": GAMEJOBS_URL,
                "company": "teamLFG",
                "job_title": "Operations Director",
                "job_description": "Posted 20 hours ago. Lead business operations and cross-functional studio planning.",
            }
        )
        messages = app.prospect_warning_messages(gamejobs_intelligence)
        self.assertTrue(any("GameJobs.co" in message for message in messages))
        self.assertTrue(any("Original posting should be confirmed" in message for message in messages))

        preview = app.import_failure_preview(
            GREENHOUSE_URL,
            "The page did not provide a complete title, company, and job description.",
        )
        self.assertEqual(preview["verification"]["source_name"], "Greenhouse")
        self.assertEqual(preview["verification"]["source_type"], "Employer ATS")
        self.assertIn("Paste the job description manually", preview["message"])


class Sprint142DashboardTests(unittest.TestCase):
    def test_dashboard_corrects_gamejobs_source_and_shows_warnings(self):
        record = enrich_dashboard_record(
            {
                "id": "teamlfg_ops",
                "company": "teamLFG",
                "role": "Operations Director",
                "official_url": GAMEJOBS_URL,
                "source": "Company career page",
                "source_name": "Company career page",
                "source_type": "Direct Employer",
                "source_trust_label": "Direct Employer",
                "verification_status": "Employer Source",
                "field_warnings": ["Location was not detected. Review before saving."],
                "job_description": "Posted 20 hours ago.",
                "match_score": 88,
                "match_tier": "Strong Match",
                "recommended_action": "Generate Package",
                "show_on_dashboard": True,
            },
            TODAY,
        )
        self.assertEqual(record["source_name"], "GameJobs.co")
        self.assertEqual(record["source_type"], "Gaming Industry Job Board")
        self.assertEqual(record["verification_status"], "Industry Board")
        self.assertIn("Original posting should be confirmed", source_verification_caution(record))
        self.assertIn("Open original posting", recommended_next_steps([record], "Apply Mode")[0])

        html = _render_metadata({"tracker": record})
        for value in ("GameJobs.co", "Gaming Industry Job Board", "Industry Board", "High"):
            self.assertIn(value, html)
        notes = _render_notes(record)
        self.assertIn("Field warnings", notes)
        self.assertIn("Location was not detected", notes)


if __name__ == "__main__":
    unittest.main()
