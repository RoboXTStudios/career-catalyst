import unittest
import shutil
import tempfile
from pathlib import Path

import app
from scripts.application_tracker import load_application_tracker
from scripts.dynamic_role_intelligence import detect_role_family
from scripts.filename_utils import company_display_name
from scripts.generate_application_note import (
    _application_note_content,
    generate_application_note,
)
from scripts.generate_cover_letter import (
    _cover_letter_content,
    generate_cover_letter,
    load_generation_context,
)
from scripts.generate_messages import (
    _hiring_manager_content,
    _recruiter_content,
    generate_message,
)
from scripts.package_generator import build_package_context
from scripts.role_context import is_google_youtube_role


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NETFLIX_ID = "netflix_inc_program_manager_design"
NETFLIX_JOB = "jobs/netflix_inc_program_manager_design.md"
GOOGLE_JOB = "jobs/google_strategy_ops_lead_youtube_auction_brand.md"
STALE_TERMS = (
    "google opportunity",
    "youtube product activation",
    "youtube brand auction",
    "seller enablement",
    "large advertiser execution",
)


def _material_inputs(context):
    return "\n".join(
        (
            _application_note_content(context),
            _recruiter_content(context),
            _hiring_manager_content(context),
            _cover_letter_content(context),
        )
    ).lower()


class NetflixContextRegressionTests(unittest.TestCase):
    def test_generic_go_to_market_text_does_not_make_netflix_a_google_role(self):
        context = load_generation_context(NETFLIX_JOB, PROJECT_ROOT)
        self.assertFalse(is_google_youtube_role(context["parsed_job"]))
        self.assertNotEqual(context["role_family"], "gtm_product_activation")
        for term in STALE_TERMS:
            self.assertNotIn(term, _material_inputs(context))

    def test_google_specific_role_still_keeps_google_calibration(self):
        context = load_generation_context(GOOGLE_JOB, PROJECT_ROOT)
        self.assertTrue(is_google_youtube_role(context["parsed_job"]))
        self.assertEqual(context["role_family"], "gtm_product_activation")
        self.assertIn("youtube product activation", _material_inputs(context))

    def test_google_seeded_session_is_cleared_before_netflix_context_build(self):
        state = {
            "package_preview_prospect_id": "google_strategy_ops_youtube_auction_brand",
            "last_package_outputs": {"recruiter_message": "google.md"},
            "last_package_result": {"tracker_id": "google_strategy_ops_youtube_auction_brand"},
            "package_role_intelligence": {"role_family": "gtm_product_activation"},
            "package_intelligence_preview": "YouTube product activation",
            "package_suggested_cover_letter_angle": "seller enablement",
            "package_suggested_proof_points": ["large advertiser execution"],
            "package_company_voice": "google_youtube",
            "package_company_category": "product_technology",
            "package_role_family": "gtm_product_activation",
        }
        self.assertTrue(app.reset_package_preview_for_selection(state, NETFLIX_ID))
        self.assertEqual(state, {"package_preview_prospect_id": NETFLIX_ID})

        context = build_package_context(
            NETFLIX_ID, load_application_tracker(PROJECT_ROOT), PROJECT_ROOT
        )
        self.assertEqual(context["company"], "Netflix")
        self.assertEqual(context["role_title"], "Program Manager, Design")
        self.assertIn("netflix.wd108.myworkdayjobs.com", context["source_url"])
        isolated_input = " ".join(
            (
                context["company"],
                context["role_title"],
                context["source_url"],
                context["job_description"],
                str(context["role_intelligence"]),
            )
        ).lower()
        for term in STALE_TERMS:
            self.assertNotIn(term, isolated_input)

    def test_contexts_remain_isolated_in_both_generation_orders(self):
        netflix_first = load_generation_context(NETFLIX_JOB, PROJECT_ROOT)
        google_second = load_generation_context(GOOGLE_JOB, PROJECT_ROOT)
        google_first = load_generation_context(GOOGLE_JOB, PROJECT_ROOT)
        netflix_second = load_generation_context(NETFLIX_JOB, PROJECT_ROOT)

        self.assertNotIn("google opportunity", _material_inputs(netflix_first))
        self.assertIn("youtube product activation", _material_inputs(google_second))
        self.assertIn("youtube product activation", _material_inputs(google_first))
        self.assertNotIn("seller enablement", _material_inputs(netflix_second))

    def test_netflix_legal_name_has_clean_display_name(self):
        self.assertEqual(company_display_name("Netflix, Inc."), "Netflix")

    def test_clean_netflix_materials_write_successfully_in_temp_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ("data", "config"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            (root / "jobs").mkdir()
            shutil.copy2(PROJECT_ROOT / NETFLIX_JOB, root / NETFLIX_JOB)

            results = (
                generate_application_note(NETFLIX_JOB, root),
                generate_message("recruiter", NETFLIX_JOB, root),
                generate_message("hiring-manager", NETFLIX_JOB, root),
                generate_cover_letter(NETFLIX_JOB, root),
            )
            combined = "\n".join(
                Path(result["output_path"]).read_text(encoding="utf-8")
                for result in results
            ).lower()
            self.assertIn("netflix", combined)
            for term in STALE_TERMS:
                self.assertNotIn(term, combined)


class IntakeStateTests(unittest.TestCase):
    def test_new_url_clears_previous_role_fields_before_import(self):
        state = {
            "prospect_context_url": "https://careers.google.com/old-role",
            "prospect_url": "https://jobs.netflix.com/new-role",
            "prospect_company": "Google",
            "prospect_role": "Strategy and Operations Lead",
            "prospect_location": "Mountain View",
            "prospect_salary": "$1",
            "prospect_posting_date": "2026-01-01",
            "prospect_description": "YouTube product activation and seller enablement.",
            "prospect_job_id": "google-role",
        }

        def fail(_url):
            raise ValueError("blocked")

        app.apply_prospect_url_import_state(state, fail)
        self.assertNotEqual(state.get("prospect_company"), "Google")
        self.assertNotIn("YouTube", state.get("prospect_description", ""))
        self.assertTrue(state["prospect_intelligence_stale"])

    def test_role_defining_field_change_marks_intelligence_stale(self):
        state = {"prospect_intelligence_stale": False}
        app.mark_prospect_intelligence_stale(state)
        self.assertTrue(state["prospect_intelligence_stale"])
        self.assertIn("Re-parse and re-score", state["prospect_import_result"][1])

    def test_gtm_in_description_alone_is_not_product_activation_family(self):
        family = detect_role_family(
            "Program Manager, Design",
            "Coordinate design delivery with broader go-to-market plans.",
        )
        self.assertNotEqual(family, "gtm_product_activation")


if __name__ == "__main__":
    unittest.main()
