import unittest
from pathlib import Path

import app

from scripts.company_voice import (
    company_voice_context,
    detect_company_voice_profile,
    detect_role_family,
)
from scripts.generate_application_note import generate_application_note
from scripts.generate_cover_letter import generate_cover_letter
from scripts.generate_messages import generate_message
from scripts.load_data import load_yaml_file
from scripts.parse_job import parse_job_description


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS = {
    "disney": "jobs/director_strategy_operations_product_technology_disney_entertainment_and_espn_product_technology.md",
    "google_youtube": "jobs/google_strategy_ops_lead_youtube_auction_brand.md",
    "paramount": "jobs/paramount_director_marketing_operations.md",
    "uta": "jobs/director_transformation_united_talent_agency.md",
    "fieldai": "jobs/director_of_matrix_operations_organizational_efficiency_fieldai.md",
    "bandsintown": "jobs/senior_copywriter_content_strategist_bandsintown.md",
    "crunchyroll": "jobs/sample_job_description.md",
}
BANNED_PHRASES = (
    "I am writing to express my interest",
    "perfect fit",
    "thrilled",
    "synergies",
    "rockstar",
    "ninja",
)


class CompanyVoiceProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile_config = load_yaml_file(
            "config/company_voice_profiles.yml", PROJECT_ROOT
        )
        cls.results = {
            key: generate_cover_letter(job, PROJECT_ROOT)
            for key, job in JOBS.items()
        }
        cls.contents = {
            key: Path(result["output_path"]).read_text(encoding="utf-8")
            for key, result in cls.results.items()
        }

    def test_company_voice_profiles_load_successfully(self):
        profiles = self.profile_config["company_voice_profiles"]
        self.assertEqual(
            set(profiles),
            {
                "disney",
                "google_youtube",
                "paramount",
                "uta",
                "fieldai",
                "bandsintown",
                "crunchyroll",
            },
        )
        for profile in profiles.values():
            self.assertTrue(profile["companies"])
            self.assertTrue(profile["tone"])
            self.assertTrue(profile["cover_letter_angle"])
            self.assertTrue(profile["avoid"])

    def test_company_names_detect_expected_profiles(self):
        expected = {
            "Disney Entertainment and ESPN Product & Technology": "disney",
            "Google": "google_youtube",
            "Paramount": "paramount",
            "United Talent Agency": "uta",
            "FieldAI": "fieldai",
            "BandsInTown": "bandsintown",
            "Crunchyroll": "crunchyroll",
        }
        for company, profile_key in expected.items():
            detected, _profile = detect_company_voice_profile(
                company, self.profile_config
            )
            self.assertEqual(detected, profile_key)

    def test_role_family_detection_covers_current_company_roles(self):
        expected = {
            "disney": "product_strategy_ops",
            "google_youtube": "gtm_product_activation",
            "paramount": "creative_marketing_ops",
            "uta": "transformation_advisory",
            "fieldai": "ai_operations_systems",
            "bandsintown": "music_content_strategy",
            "crunchyroll": "streaming_strategy",
        }
        for profile_key, family in expected.items():
            parsed = parse_job_description(PROJECT_ROOT / JOBS[profile_key])
            self.assertEqual(detect_role_family(parsed), family)
            context = company_voice_context(parsed, self.profile_config)
            self.assertEqual(context["profile_key"], profile_key)

    def test_disney_letter_has_product_enterprise_entertainment_tone(self):
        content = self.contents["disney"]
        self.assertIn("product and technology strategy", content.lower())
        self.assertIn("large entertainment enterprise", content.lower())
        self.assertIn("Disney Studios Theatrical", content)
        self.assertNotIn("Substack", content)
        self.assertNotIn("music, audience connection", content.lower())

    def test_google_letter_is_product_and_gtm_specific_without_employment_claims(self):
        content = self.contents["google_youtube"]
        self.assertIn("YouTube product activation", content)
        self.assertIn("GTM operations", content)
        self.assertIn("seller enablement", content)
        for phrase in (
            "worked at Google",
            "Google employee",
            "inside Google",
            "family connection",
            "internal referral",
        ):
            self.assertNotIn(phrase.lower(), content.lower())

    def test_paramount_letter_centers_creative_marketing_operations(self):
        content = self.contents["paramount"].lower()
        self.assertIn("marketing operations", content)
        self.assertIn("creative capacity", content)
        self.assertIn("campaignos", content)

    def test_uta_letter_uses_transformation_advisory_language(self):
        content = self.contents["uta"].lower()
        self.assertIn("transformation", content)
        self.assertIn("advisory", content)
        self.assertIn("operating model", content)
        self.assertIn("client-facing", content)

    def test_fieldai_letter_centers_matrix_and_ai_operations(self):
        content = self.contents["fieldai"].lower()
        self.assertIn("matrix operations", content)
        self.assertIn("organizational efficiency", content)
        self.assertIn("automation", content)
        self.assertIn("campaignos", content)

    def test_bandsintown_letter_is_music_aware_editorial_and_human(self):
        content = self.contents["bandsintown"]
        lowered = content.lower()
        self.assertIn("music", lowered)
        self.assertIn("audience connection", lowered)
        self.assertIn("Substack", content)
        self.assertIn("Multiverse", content)
        self.assertIn("artists, industry partners, and fans", lowered)
        self.assertNotIn("generic marketing operations", lowered)
        self.assertNotIn("label experience", lowered)
        self.assertNotIn("artist management experience", lowered)
        self.assertNotIn("professional music journalism", lowered)

    def test_cover_letter_openings_are_meaningfully_different(self):
        openings = {
            content.split("\n\n")[1] for content in self.contents.values()
        }
        self.assertEqual(len(openings), len(self.contents))

    def test_all_company_letters_respect_tone_safeguards(self):
        for profile_key, content in self.contents.items():
            self.assertNotIn("—", content, profile_key)
            lowered = content.lower()
            for phrase in BANNED_PHRASES:
                self.assertNotIn(phrase.lower(), lowered, profile_key)

    def test_bandsintown_messages_and_note_receive_light_voice_influence(self):
        recruiter = generate_message("recruiter", JOBS["bandsintown"], PROJECT_ROOT)
        manager = generate_message(
            "hiring-manager", JOBS["bandsintown"], PROJECT_ROOT
        )
        note = generate_application_note(JOBS["bandsintown"], PROJECT_ROOT)
        materials = [
            Path(result["output_path"]).read_text(encoding="utf-8")
            for result in (recruiter, manager, note)
        ]
        for content in materials:
            self.assertIn("music", content.lower())
            self.assertTrue("Substack" in content or "Multiverse" in content)

    def test_generation_results_expose_detected_context(self):
        for profile_key, result in self.results.items():
            self.assertEqual(result["company_voice_profile"], profile_key)
            self.assertIn(
                result["role_family"],
                {
                    "creative_marketing_ops",
                    "product_strategy_ops",
                    "transformation_advisory",
                    "music_content_strategy",
                    "ai_operations_systems",
                    "streaming_strategy",
                    "gtm_product_activation",
                },
            )

    def test_ui_helper_exposes_company_voice_and_role_family(self):
        context = app.detected_application_voice(
            "bandsintown_senior_copywriter_content_strategist", PROJECT_ROOT
        )
        self.assertEqual(context["profile_label"], "Bandsintown")
        self.assertEqual(context["role_family"], "music_content_strategy")


if __name__ == "__main__":
    unittest.main()
