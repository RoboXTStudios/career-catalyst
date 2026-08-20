import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.generate_application_note import generate_application_note
from scripts.generate_cover_letter import generate_cover_letter
from scripts.generate_messages import generate_message


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
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        for directory in ("data", "config", "templates", "jobs"):
            shutil.copytree(PROJECT_ROOT / directory, cls.root / directory)
        cls.results = {
            "cover_letter": generate_cover_letter(SAMPLE_JOB, cls.root),
            "recruiter": generate_message("recruiter", SAMPLE_JOB, cls.root),
            "hiring_manager": generate_message("hiring-manager", SAMPLE_JOB, cls.root),
            "application_note": generate_application_note(SAMPLE_JOB, cls.root),
        }
        cls.contents = {
            name: Path(result["output_path"]).read_text(encoding="utf-8")
            for name, result in cls.results.items()
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

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

        self.assertIn("milestones, dependencies, risks", content)
        self.assertIn("shared priorities, clear ownership", content)

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
        self.assertTrue(content.startswith("Dear Crunchyroll Hiring Team,"))

    def test_materials_stay_within_word_limits(self):
        limits = {
            "cover_letter": (250, 325),
            "recruiter": (80, 130),
            "hiring_manager": (120, 180),
            # Current application notes may include a concise positive transfer
            # paragraph and are intentionally allowed up to 230 words.
            "application_note": (60, 230),
        }
        for name, content in self.contents.items():
            minimum, maximum = limits[name]
            self.assertGreaterEqual(_word_count(content), minimum)
            self.assertLessEqual(_word_count(content), maximum)


if __name__ == "__main__":
    unittest.main()


class BannedVoiceRewriteTests(unittest.TestCase):
    def test_azira_style_generation_rewrites_clear_plan_before_validation(self):
        from scripts.generate_cover_letter import save_material

        with tempfile.TemporaryDirectory() as temporary:
            context = {
                "root": Path(temporary),
                "parsed_job": {
                    "job_title": "Director, Chief of Staff & Business Operations",
                    "company": "Azira",
                    "raw_text": "chief of staff business operations leadership team operating cadence",
                },
                "career_data": {"data": {"personal_brand": {"candidate": {"name": "Trisha Lynch"}}}},
                "match_report": {"match_score": 90},
                "voice": {"avoid": []},
                "writing_voice": {"banned_phrases": []},
                "material_editing_plan": {"banned_phrases": ["clear plan"]},
            }
            content = " ".join(["A clear plan helps Azira operating cadence."] * 8)

            result = save_material(context, "Cover_Letter", content, 5, 200)
            saved = Path(result["output_path"]).read_text(encoding="utf-8")

        self.assertIn("clear operating structure", saved)
        self.assertNotIn("clear plan", saved.lower())
        self.assertIn("clear plan", result["warnings"][0])

    def test_banned_phrase_validation_fails_when_unrewriteable_phrase_remains(self):
        from scripts.generate_cover_letter import ApplicationMaterialError, save_material

        context = {
            "root": PROJECT_ROOT,
            "parsed_job": {
                "job_title": "Director, Operations",
                "company": "Azira",
                "raw_text": "operations leadership cadence",
            },
            "career_data": {"data": {"personal_brand": {"candidate": {"name": "Trisha Lynch"}}}},
            "match_report": {"match_score": 90},
            "voice": {"avoid": []},
            "writing_voice": {"banned_phrases": []},
            "material_editing_plan": {"banned_phrases": ["unrewriteable banned phrase"]},
        }
        content = " ".join(["This unrewriteable banned phrase remains in the material."] * 8)

        with self.assertRaises(ApplicationMaterialError):
            save_material(context, "Cover_Letter", content, 5, 200)
