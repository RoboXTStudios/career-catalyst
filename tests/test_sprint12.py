import re
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

from scripts.application_tracker import add_prospect, load_application_tracker
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.generate_cover_letter import generate_cover_letter
from scripts.job_freshness import detect_job_freshness
from scripts.package_generator import PackageGenerationError, generate_package
from scripts.prospect_intake import create_prospect


def _words(count):
    return " ".join(f"word{index}" for index in range(count))


def _word_count(text):
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


class CoverLetterRepairTests(unittest.TestCase):
    def _generate(self, body):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        context = {
            "root": root,
            "parsed_job": {
                "job_title": "Director, Business Operations",
                "company": "Acme Music",
                "raw_text": "Lead business operations and workflow systems.",
            },
            "career_data": {"data": {"personal_brand": {"candidate": {"name": "Trisha Lynch"}}}},
            "match_report": {"match_score": 80},
            "voice": {"avoid": []},
            "role_family": "business_operations",
            "company_category": "music_entertainment_operations",
            "profile_key": "dynamic_music_entertainment_operations",
            "profile_source": "dynamic_inference",
            "effective_voice_profile": {"confidence": 0.7},
        }
        with patch("scripts.generate_cover_letter.load_generation_context", return_value=context), patch(
            "scripts.generate_cover_letter._cover_letter_content", return_value=body
        ):
            result = generate_cover_letter("unused.md", root)
        content = Path(result["output_path"]).read_text(encoding="utf-8")
        temporary.cleanup()
        return result, content

    def test_under_250_words_auto_expands_successfully(self):
        result, content = self._generate("Hello,\n\n" + _words(190) + "\n\nSincerely,\nTrisha")
        self.assertGreaterEqual(_word_count(content), 250)
        self.assertLessEqual(_word_count(content), 400)
        self.assertGreater(result["repair_attempts"], 0)

    def test_over_400_words_auto_trims_successfully(self):
        result, content = self._generate("Hello,\n\n" + _words(440) + ".\n\nSincerely,\nTrisha")
        self.assertGreaterEqual(_word_count(content), 250)
        self.assertLessEqual(_word_count(content), 400)
        self.assertGreater(result["repair_attempts"], 0)

    def test_248_word_cover_letter_no_longer_fails(self):
        # Greeting and signoff are included in the requested 248-word boundary case.
        result, content = self._generate("Hello,\n\n" + _words(244) + "\n\nSincerely,\nTrisha")
        self.assertGreaterEqual(result["word_count"], 250)
        self.assertNotIn("must be 250-400 words", content)


class FreshnessAndIntelligenceTests(unittest.TestCase):
    def test_stale_posting_detection(self):
        result = detect_job_freshness("Posted: May 1, 2026", today=date(2026, 6, 30))
        self.assertEqual(result["category"], "Stale")
        self.assertEqual(result["age_days"], 60)

    def test_wmg_strategic_operations_role_classifies_as_music_operations(self):
        result = get_effective_voice_profile(
            "Warner Chappell Music",
            "Sr. Manager, Strategic Integration & Operations",
            "Lead operational strategy, transformation, systems integration, and process improvement for a music publishing business.",
        )
        self.assertEqual(result["company_category"], "music_entertainment_operations")
        self.assertEqual(result["role_family"], "business_operations")
        self.assertEqual(result["company_voice_label"], "Music + Operational Transformation")
        self.assertEqual(result["company_category_label"], "Music / Entertainment Operations")


class PackageReliabilityTests(unittest.TestCase):
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

    def _job(self, closed=False):
        path = self.root / "jobs" / "director_operations_nova.md"
        closing = " Applications closed." if closed else " Posted 3 days ago."
        path.write_text(
            "# Director, Business Operations\n\n"
            "Company: Nova Creative Technology\n"
            "Tracker ID: nova_director_operations\n\n"
            "## Job Description\n\n"
            "Lead business operations, AI workflow systems, process improvement, and cross-functional strategy "
            "for a remote creative technology company." + closing,
            encoding="utf-8",
        )
        add_prospect(
            {
                "id": "nova_director_operations",
                "company": "Nova Creative Technology",
                "role": "Director, Business Operations",
                "status": "Drafted",
                "priority": "High",
                "job_file": "jobs/director_operations_nova.md",
                "show_on_dashboard": True,
            },
            self.root,
        )
        return path

    def _generate_with_core_outputs_mocked(self):
        result_path = lambda name: {"output_path": str(self.root / "exports" / name)}
        with ExitStack() as stack:
            stack.enter_context(patch("scripts.package_generator.score_job_match", return_value={
                "match_score": 86,
                "match_band": "Strong",
                "missing_keywords": [],
                "top_matching_skills": ["Business Operations", "AI Workflow Design"],
            }))
            stack.enter_context(patch("scripts.package_generator.tailor_resume", return_value=result_path("resume.md")))
            stack.enter_context(patch("scripts.package_generator.export_styled_docx", return_value=result_path("styled.docx")))
            stack.enter_context(patch("scripts.package_generator.export_ats_docx", return_value=result_path("ats.docx")))
            stack.enter_context(patch("scripts.package_generator.generate_cover_letter", return_value={**result_path("cover.md"), "txt_output_path": str(self.root / "exports/cover.txt"), "word_count": 300}))
            stack.enter_context(patch("scripts.package_generator.generate_message", side_effect=[result_path("recruiter.md"), result_path("manager.md")]))
            stack.enter_context(patch("scripts.package_generator.generate_application_note", return_value=result_path("note.md")))
            stack.enter_context(patch("scripts.package_generator.generate_strategy_pack", return_value=result_path("strategy.md")))
            stack.enter_context(patch("scripts.package_generator.generate_interview_prep", return_value=result_path("interview.md")))
            stack.enter_context(patch("scripts.package_generator.generate_dashboard", return_value=result_path("dashboard.html")))
            return generate_package("nova_director_operations", self.root)

    def test_closed_posting_blocks_generation(self):
        self._job(closed=True)
        with patch("scripts.package_generator.tailor_resume") as generator:
            with self.assertRaises(PackageGenerationError) as context:
                generate_package("nova_director_operations", self.root)
        generator.assert_not_called()
        self.assertIn("appears closed", str(context.exception))
        # A blocked package run is transactional: detection must not mutate the
        # previously valid tracker record.
        self.assertNotIn("posting_status", load_application_tracker(self.root)[0])

    def test_unknown_salary_does_not_break_package_generation(self):
        self._job()
        result = self._generate_with_core_outputs_mocked()
        application = load_application_tracker(self.root)[0]
        self.assertEqual(application["salary_range"], "Not disclosed")
        self.assertIn("opportunity", result)
        self.assertIn("package_quality", result)

    def test_new_company_without_hardcoded_profile_generates_package(self):
        self._job()
        result = self._generate_with_core_outputs_mocked()
        self.assertEqual(result["company_voice_source"], "dynamic_inference")
        self.assertIn("interview_prep", result["outputs"])
        self.assertIn("package_summary", result["outputs"])

    def test_pasted_description_can_supply_company_and_role(self):
        description = (
            "# Director, Business Operations\n\nCompany: New World Systems\n\n"
            "Lead business operations, workflow design, strategic planning, and cross-functional execution "
            "for a growing creative technology organization with remote teams across the United States."
        )
        result = create_prospect({"job_description": description}, self.root)
        self.assertEqual(result["application"]["company"], "New World Systems")
        self.assertEqual(result["application"]["role"], "Director, Business Operations")
        self.assertEqual(result["application"]["salary_range"], "Not disclosed")


if __name__ == "__main__":
    unittest.main()
