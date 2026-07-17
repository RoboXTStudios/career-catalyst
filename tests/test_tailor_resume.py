import unittest
from pathlib import Path

from scripts.load_data import load_all_yaml
from scripts.tailor_resume import _selected_projects, tailor_resume


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

    def test_generated_resume_excludes_personal_projects(self):
        result = tailor_resume("executive_operations", SAMPLE_JOB, PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")

        for term in ("Career Catalyst", "CampaignOS", "Substack"):
            self.assertNotIn(term, content)

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


def _project_names_and_bullet_counts(parsed_job, resume_profile="executive_operations"):
    projects = _selected_projects(load_all_yaml(PROJECT_ROOT), parsed_job, resume_profile)
    return {project["name"]: len(bullets) for project, bullets in projects}


def test_azira_style_resume_omits_personal_projects():
    parsed_job = {
        "job_title": "Director, Chief of Staff & Business Operations",
        "company": "Azira",
        "raw_text": "chief of staff business operations leadership team operating cadence planning rhythms ownership risk surfacing follow-through",
        "keywords": ["chief of staff", "business operations", "operating cadence"],
    }
    projects = _project_names_and_bullet_counts(parsed_job)
    assert "Substack Writer" not in projects
    assert "OMG23 Multiverse Newsletter" not in projects
    assert "CampaignOS" not in projects


def test_product_ai_resume_still_omits_personal_projects():
    parsed_job = {
        "job_title": "AI Product Manager",
        "company": "Netflix",
        "raw_text": "AI product manager platform operations workflow automation internal tools systems design roadmap",
        "keywords": ["AI product", "workflow automation", "internal tools", "systems design"],
    }
    projects = _project_names_and_bullet_counts(parsed_job, "product_ai")
    assert "CampaignOS" not in projects


def test_traditional_pmo_resume_omits_creative_editorial_projects():
    parsed_job = {
        "job_title": "Senior PMO Lead",
        "company": "Example Co",
        "raw_text": "PMO program management governance delivery dependencies milestones roadmap risk management operating model content editorial",
        "keywords": ["PMO", "governance", "delivery", "content", "editorial"],
    }
    projects = _project_names_and_bullet_counts(parsed_job)
    assert "Substack Writer" not in projects
    assert "OMG23 Multiverse Newsletter" not in projects
    assert "CampaignOS" not in projects


if __name__ == "__main__":
    unittest.main()
