import unittest
import shutil
import tempfile
from pathlib import Path

from scripts.generate_strategy_pack import generate_strategy_pack


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JOB = "jobs/sample_job_description.md"


class StrategyPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        for directory in ("data", "config", "jobs"):
            shutil.copytree(PROJECT_ROOT / directory, cls.root / directory)
        cls.result = generate_strategy_pack(SAMPLE_JOB, cls.root)
        cls.output_path = Path(cls.result["output_path"])
        cls.content = cls.output_path.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_strategy_pack_file_is_generated(self):
        self.assertTrue(self.output_path.is_file())
        self.assertTrue(self.output_path.name.endswith("_strategy_pack.txt"))

    def test_strategy_pack_is_not_empty(self):
        self.assertGreater(self.output_path.stat().st_size, 0)
        self.assertTrue(self.content.strip())

    def test_strategy_pack_contains_required_sections(self):
        for heading in (
            "### Role Opportunity Brief",
            "### Why Trisha",
            "### 30/60/90-Day Plan",
            "### Strategic POV Note",
            "### Interview Talking Points",
            "### Smart Questions to Ask",
        ):
            self.assertIn(heading, self.content)

    def test_strategy_pack_contains_plan_subsections(self):
        for heading in (
            "#### First 30 Days: Listen, Map, and Understand",
            "#### Days 31-60: Prioritize, Align, and Improve",
            "#### Days 61-90: Operationalize, Scale, and Measure",
        ):
            self.assertIn(heading, self.content)

    def test_strategy_pack_contains_company_and_role(self):
        self.assertIn("Crunchyroll", self.content)
        self.assertIn("Director, Enterprise Strategy & Initiatives", self.content)

    def test_strategy_pack_uses_canonical_career_scope_without_forcing_projects(self):
        self.assertIn("OMG23 (Omnicom Media Group)", self.content)
        self.assertIn("10 direct reports", self.content)
        self.assertIn("64-person organization", self.content)
        if "CampaignOS" in self.content:
            self.assertIn("working prototype", self.content.lower())

    def test_strategy_pack_has_role_specific_talking_points_and_questions(self):
        talking_section = self.content.split("### Interview Talking Points", 1)[1].split(
            "### Smart Questions to Ask", 1
        )[0]
        question_section = self.content.split("### Smart Questions to Ask", 1)[1]

        self.assertGreaterEqual(talking_section.count("- **"), 6)
        self.assertLessEqual(talking_section.count("- **"), 8)
        question_count = sum(1 for line in question_section.splitlines() if line.startswith("- "))
        self.assertGreaterEqual(question_count, 6)
        self.assertLessEqual(question_count, 8)

    def test_strategy_pack_has_no_placeholder_or_em_dash(self):
        self.assertNotIn("placeholder", self.content.lower())
        self.assertNotIn("—", self.content)

    def test_strategy_pack_avoids_invented_familiarity_and_overpromising(self):
        lowered = self.content.lower()
        for phrase in (
            "As an insider",
            "I know your team",
            "I spoke with",
            "guaranteed",
            "perfect fit",
        ):
            self.assertNotIn(phrase.lower(), lowered)


if __name__ == "__main__":
    unittest.main()
