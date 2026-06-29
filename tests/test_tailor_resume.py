import unittest
from pathlib import Path

from scripts.tailor_resume import tailor_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JOB = "jobs/sample_job_description.md"
LINKEDIN_URL = "https://www.linkedin.com/in/trisha-lynch-3433417"
LINKEDIN_MARKDOWN = f"[{LINKEDIN_URL}]({LINKEDIN_URL})"
OLD_LINKEDIN_URL = "https://www.linkedin.com/in/trishalynch"


class TailorResumeTests(unittest.TestCase):
    def test_tailor_command_generates_markdown_file(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)

        self.assertTrue(result["output_path"].endswith(".md"))
        self.assertTrue(Path(result["output_path"]).is_file())

    def test_generated_resume_contains_trisha_lynch(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("Trisha Lynch", content)

    def test_generated_resume_contains_full_linkedin_url(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn(LINKEDIN_MARKDOWN, content)
        self.assertNotIn(OLD_LINKEDIN_URL, content)
        self.assertNotIn("LinkedIn: linkedin.com/", content)

    def test_generated_resume_contains_profile(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("## Profile", content)

    def test_generated_resume_contains_core_competencies(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("## Core Competencies", content)

    def test_generated_resume_contains_campaignos(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("CampaignOS", content)

    def test_generated_resume_preserves_canonical_platform_language(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("AI Workflow Design", content)
        self.assertIn("Process Automation", content)
        self.assertIn("Python (Working Knowledge)", content)
        self.assertIn("Newsletter Development", content)
        self.assertIn("Editorial Production", content)

    def test_generated_resume_does_not_contain_placeholder_text(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertNotIn("Placeholder", content)
        self.assertNotIn("placeholder", content)

    def test_generated_resume_output_path_exists(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)

        self.assertTrue(Path(result["output_path"]).exists())


if __name__ == "__main__":
    unittest.main()
