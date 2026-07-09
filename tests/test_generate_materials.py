import re
import unittest
from pathlib import Path

from scripts.generate_application_note import generate_application_note
from scripts.generate_cover_letter import generate_cover_letter, save_material
from scripts.generate_messages import generate_message
from scripts.load_data import load_all_yaml
from scripts.role_editing import material_editing_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JOB = "jobs/sample_job_description.md"
BANNED_PHRASES = (
    "I am writing to express my interest",
    "I believe I would be a strong fit",
    "leveraging my experience",
    "dynamic professional",
    "proven track record",
    "synergies",
    "thrilled",
    "perfect fit",
    "rockstar",
    "ninja",
)


def _word_count(text):
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


class GenerateMaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {
            "cover_letter": generate_cover_letter(SAMPLE_JOB, PROJECT_ROOT),
            "recruiter": generate_message("recruiter", SAMPLE_JOB, PROJECT_ROOT),
            "hiring_manager": generate_message("hiring-manager", SAMPLE_JOB, PROJECT_ROOT),
            "application_note": generate_application_note(SAMPLE_JOB, PROJECT_ROOT),
        }
        cls.contents = {
            name: Path(result["output_path"]).read_text(encoding="utf-8")
            for name, result in cls.results.items()
        }

    def test_cover_letter_file_is_generated(self):
        path = Path(self.results["cover_letter"]["output_path"])

        self.assertTrue(path.is_file())
        self.assertTrue(path.name.endswith("_cover_letter.txt"))

    def test_cover_letter_plain_text_file_is_generated(self):
        markdown_path = Path(self.results["cover_letter"]["output_path"])
        text_path = Path(self.results["cover_letter"]["txt_output_path"])

        self.assertTrue(text_path.is_file())
        self.assertTrue(text_path.name.endswith("_cover_letter.txt"))
        self.assertEqual(
            markdown_path.read_text(encoding="utf-8"),
            text_path.read_text(encoding="utf-8"),
        )

    def test_recruiter_message_file_is_generated(self):
        path = Path(self.results["recruiter"]["output_path"])

        self.assertTrue(path.is_file())
        self.assertTrue(path.name.endswith("_recruiter_message.txt"))

    def test_hiring_manager_message_file_is_generated(self):
        path = Path(self.results["hiring_manager"]["output_path"])

        self.assertTrue(path.is_file())
        self.assertTrue(path.name.endswith("_hiring_manager_message.txt"))

    def test_application_note_file_is_generated(self):
        path = Path(self.results["application_note"]["output_path"])

        self.assertTrue(path.is_file())
        self.assertTrue(path.name.endswith("_application_note.txt"))

    def test_generated_files_are_not_empty(self):
        for result in self.results.values():
            self.assertGreater(Path(result["output_path"]).stat().st_size, 0)

    def test_cover_letter_uses_candidate_language_and_company(self):
        content = self.contents["cover_letter"]

        self.assertTrue("Trisha Lynch" in content or " I " in content)
        self.assertIn("Crunchyroll", content)
        self.assertIn("Director, Enterprise Strategy & Initiatives", content)

    def test_cover_letter_uses_calibrated_voice(self):
        content = self.contents["cover_letter"]

        self.assertIn("What caught my attention", content)
        self.assertIn("creative and marketing teams", content)

    def test_messages_and_note_contain_company(self):
        for name in ("recruiter", "hiring_manager", "application_note"):
            self.assertIn("Crunchyroll", self.contents[name])

    def test_materials_have_no_placeholders_or_em_dashes(self):
        for content in self.contents.values():
            self.assertNotIn("placeholder", content.lower())
            self.assertNotIn("—", content)

    def test_materials_avoid_banned_voice_phrases(self):
        for content in self.contents.values():
            lowered = content.lower()
            for phrase in BANNED_PHRASES:
                self.assertNotIn(phrase.lower(), lowered)

    def test_cover_letter_avoids_generic_opening(self):
        content = self.contents["cover_letter"]

        self.assertNotIn("I am writing to express my interest", content)
        self.assertNotIn("Dear Hiring Manager", content)
        self.assertTrue(content.startswith("Hello,"))

    def test_materials_stay_within_word_limits(self):
        limits = {
            "cover_letter": (250, 400),
            "recruiter": (80, 130),
            "hiring_manager": (120, 180),
            "application_note": (60, 100),
        }
        for name, content in self.contents.items():
            minimum, maximum = limits[name]
            self.assertGreaterEqual(_word_count(content), minimum)
            self.assertLessEqual(_word_count(content), maximum)

    def test_azira_style_package_rewrites_clear_plan_before_validation(self):
        parsed_job = {
            "job_title": "Director, Chief of Staff & Business Operations",
            "company": "Azira",
            "raw_text": "chief of staff business operations leadership team operating cadence decision support",
            "keywords": ["chief of staff", "business operations", "operating cadence"],
        }
        context = {
            "root": PROJECT_ROOT,
            "parsed_job": parsed_job,
            "career_data": load_all_yaml(PROJECT_ROOT),
            "voice": {},
            "writing_voice": {"banned_phrases": ["clear plan"]},
            "material_editing_plan": material_editing_plan(parsed_job, PROJECT_ROOT),
            "match_report": {"match_score": 80},
        }
        content = (
            "Azira needs senior team operating support, and I would bring a clear plan for "
            "planning rhythms, ownership, stakeholder alignment, risks, and follow-through."
        )

        with self.assertWarnsRegex(UserWarning, "Rewrote banned voice phrases"):
            result = save_material(
                context,
                "Cover_Letter",
                content,
                minimum_words=1,
                maximum_words=100,
            )

        saved = Path(result["output_path"]).read_text(encoding="utf-8").lower()
        self.assertNotIn("clear plan", saved)
        self.assertIn("usable operating plan", saved)


if __name__ == "__main__":
    unittest.main()
