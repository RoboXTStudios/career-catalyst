import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from scripts.application_tracker import VALID_STATUSES, get_record_status, load_application_tracker
from scripts.cli import main
from scripts.dynamic_role_intelligence import (
    build_dynamic_voice_profile,
    detect_company_voice,
    detect_role_family,
    get_effective_voice_profile,
    infer_company_context,
)
from scripts.generate_application_note import (
    _application_note_content,
    generate_application_note,
)
from scripts.generate_cover_letter import (
    _cover_letter_content,
    generate_cover_letter,
    load_generation_context,
)
from scripts.generate_followups import (
    FollowupGenerationError,
    generate_followups,
    generate_missing_followups,
)
from scripts.generate_messages import (
    _hiring_manager_content,
    _recruiter_content,
    generate_message,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BANDSINTOWN_ID = "bandsintown_senior_copywriter_content_strategist"
BANNED_PHRASES = (
    "I am writing to express my interest",
    "perfect fit",
    "thrilled",
    "synergies",
    "rockstar",
    "ninja",
    "just checking in",
    "top of your inbox",
)


class DynamicRoleIntelligenceTests(unittest.TestCase):
    def test_bandsintown_maps_to_music_company_and_role_context(self):
        profile = get_effective_voice_profile(
            company_name="BandsInTown",
            job_title="Senior Copywriter & Content Strategist",
            job_description="Write for artists, venues, promoters, and music fans.",
        )
        self.assertEqual(profile["company_category"], "music_live_events")
        self.assertIn(
            profile["role_family"],
            {"music_content_strategy", "editorial_content_strategy"},
        )
        self.assertEqual(profile["source"], "known_profile")

    def test_unknown_music_company_uses_dynamic_inference(self):
        profile = detect_company_voice(
            "Pulse House",
            "Senior Content Strategist",
            "Build content for concert discovery, touring artists, venues, and fans.",
        )
        self.assertEqual(profile["source"], "dynamic_inference")
        self.assertEqual(profile["company_category"], "music_live_events")
        self.assertEqual(profile["role_family"], "music_content_strategy")
        self.assertTrue(profile["cover_letter_angle"])
        self.assertTrue(profile["proof_points_to_emphasize"])

    def test_unknown_ai_company_with_matrix_role_is_ai_operations(self):
        profile = build_dynamic_voice_profile(
            "Nova Robotics",
            "Director of Matrix Operations",
            "An AI startup improving automation, capacity planning, and operating cadences.",
        )
        self.assertEqual(profile["company_category"], "ai_technology_startup")
        self.assertEqual(profile["role_family"], "ai_operations_systems")

    def test_short_company_and_ai_signals_do_not_match_inside_other_words(self):
        context = infer_company_context(
            "Futura Works",
            "Director of Operations",
            "Maintain capacity planning and decision cadences for a growing business.",
        )
        family = detect_role_family(
            "Director of Matrix Operations",
            "Maintain capacity planning and decision cadences for a growing business.",
        )

        self.assertNotEqual(context["company_category"], "talent_agency_media")
        self.assertEqual(family, "business_operations")

    def test_unknown_streaming_company_maps_to_streaming_strategy(self):
        context = infer_company_context(
            "StreamForge",
            "Director, Strategy & Operations",
            "Lead streaming, studio, franchise, and IP priorities across entertainment teams.",
        )
        family = detect_role_family(
            "Director, Strategy & Operations",
            "Lead streaming, studio, franchise, and IP priorities across entertainment teams.",
        )
        self.assertEqual(context["company_category"], "entertainment_streaming")
        self.assertEqual(family, "streaming_strategy")

    def test_known_companies_use_known_profiles(self):
        expected = {
            "United Talent Agency": "uta",
            "Disney Entertainment": "disney",
            "Google": "google_youtube",
        }
        for company, profile_name in expected.items():
            profile = get_effective_voice_profile(company_name=company)
            self.assertEqual(profile["source"], "known_profile")
            self.assertEqual(profile["profile_name"], profile_name)

    def test_unknown_company_never_fails_or_requires_a_profile(self):
        profile = get_effective_voice_profile(
            company_name="Acme Cooperative",
            job_title="Director of Business Operations",
            job_description="Lead planning, team operations, and executive reporting.",
        )
        self.assertEqual(profile["source"], "dynamic_inference")
        self.assertEqual(profile["role_family"], "business_operations")
        for field in (
            "profile_name",
            "company_name",
            "source",
            "company_category",
            "role_family",
            "tone",
            "cover_letter_angle",
            "proof_points_to_emphasize",
            "proof_points_to_avoid",
            "avoid",
            "confidence",
            "reasoning_summary",
        ):
            self.assertIn(field, profile)

    def test_unknown_company_materials_use_dynamic_context_and_safeguards(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for directory in ("data", "config", "templates"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            (root / "jobs").mkdir()
            job_path = root / "jobs" / "nova_robotics.md"
            job_path.write_text(
                "\n".join(
                    (
                        "# Director of Matrix Operations",
                        "",
                        "Company: Nova Robotics",
                        "",
                        "## Job Description",
                        "",
                        "Lead matrix operations, organizational efficiency, capacity planning, ",
                        "operating cadences, dashboards, and automation for an AI robotics startup. ",
                        "Partner with product, engineering, and business leaders on accountable execution.",
                    )
                ),
                encoding="utf-8",
            )
            context = load_generation_context(job_path, root)
            materials = (
                _cover_letter_content(context),
                _recruiter_content(context),
                _hiring_manager_content(context),
                _application_note_content(context),
            )
            generated = (
                generate_cover_letter(job_path, root),
                generate_message("recruiter", job_path, root),
                generate_message("hiring-manager", job_path, root),
                generate_application_note(job_path, root),
            )
            for result in generated:
                self.assertTrue(Path(result["output_path"]).is_file())
                for companion_key in ("txt_output_path", "docx_output_path"):
                    if result.get(companion_key):
                        self.assertTrue(Path(result[companion_key]).is_file())

        self.assertEqual(
            context["effective_voice_profile"]["source"], "dynamic_inference"
        )
        self.assertEqual(context["company_category"], "ai_technology_startup")
        for content in materials:
            self.assertIn("Nova Robotics", content)
            self.assertNotIn("—", content)
            lowered = content.lower()
            for phrase in BANNED_PHRASES:
                self.assertNotIn(phrase.lower(), lowered)
    def test_detect_role_cli_prints_normalized_intelligence(self):
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = main(
                [
                    "detect-role",
                    "jobs/senior_copywriter_content_strategist_bandsintown.md",
                ]
            )
        rendered = output.getvalue()
        self.assertEqual(return_code, 0)
        self.assertIn("Company category: music_live_events", rendered)
        self.assertIn("Role family: music_content_strategy", rendered)
        self.assertIn("Voice profile: bandsintown", rendered)
        self.assertIn("Source: known_profile", rendered)

    def test_bandsintown_followups_generate_for_tracker_entry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for directory in ("config", "data", "jobs"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            tracker_path = root / "data" / "application_tracker.yml"
            tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
            application = next(
                item for item in tracker["applications"] if item["id"] == BANDSINTOWN_ID
            )
            application.update(
                {
                    "status": "Applied",
                    "submitted_date": "2026-07-01",
                    "recruiter_email": "recruiter@example.com",
                    "show_on_dashboard": True,
                    "follow_up_status": "Due now",
                    "follow_up_sent": False,
                    "application_history": [],
                }
            )
            tracker_path.write_text(yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8")

            result = generate_followups(BANDSINTOWN_ID, root)
            self.assertEqual(result["status"], "Applied")
            self.assertEqual(result["company_category"], "music_live_events")
            self.assertEqual(result["role_family"], "music_content_strategy")
            for path_value in result["outputs"].values():
                path = Path(path_value)
                self.assertTrue(path.is_file())
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("—", content)
                for phrase in BANNED_PHRASES:
                    self.assertNotIn(phrase.lower(), content.lower())

    def test_followups_all_skips_or_generates_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for directory in ("config", "data", "jobs"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            tracker_path = root / "data" / "application_tracker.yml"
            tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
            for application in tracker["applications"]:
                application["show_on_dashboard"] = application["id"] == BANDSINTOWN_ID
                if application["id"] == BANDSINTOWN_ID:
                    application.update(
                        {
                            "status": "Applied",
                            "submitted_date": "2026-07-01",
                            "recruiter_email": "recruiter@example.com",
                            "follow_up_status": "Due now",
                            "follow_up_sent": False,
                            "application_history": [],
                        }
                    )
            tracker_path.write_text(yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8")

            result = generate_missing_followups(root)
            self.assertEqual(result["failed_count"], 0)
            self.assertEqual(
                result["generated_count"] + result["skipped_existing_count"], 1
            )

    def test_reviewed_role_without_job_file_gets_pre_application_networking(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(PROJECT_ROOT / "config", root / "config")
            shutil.copytree(PROJECT_ROOT / "data", root / "data")
            (root / "jobs").mkdir()
            (root / "data" / "application_tracker.yml").write_text(
                yaml.safe_dump(
                    {
                        "applications": [
                            {
                                "id": "acme_editorial_lead",
                                "company": "Acme Cooperative",
                                "company_aliases": [],
                                "role": "Editorial Content Lead",
                                "role_aliases": [],
                                "status": "Reviewed",
                                "priority": "Medium",
                                "source": "Official career page",
                                "notes": "",
                                "next_action": "Build relationships before applying.",
                                "show_on_dashboard": True,
                                "job_description": "Lead editorial strategy, content planning, and community storytelling.",
                            }
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(FollowupGenerationError) as context:
                generate_followups("acme_editorial_lead", root)

        self.assertIn("being considered and has not been applied", str(context.exception))

    def test_considered_role_generates_only_when_explicitly_selected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            shutil.copytree(PROJECT_ROOT / "config", root / "config")
            shutil.copytree(PROJECT_ROOT / "data", root / "data")
            (root / "jobs").mkdir()
            (root / "data" / "application_tracker.yml").write_text(
                yaml.safe_dump(
                    {
                        "applications": [
                            {
                                "id": "acme_considered_operations",
                                "company": "Acme Cooperative",
                                "company_aliases": [],
                                "role": "Director of Business Operations",
                                "role_aliases": [],
                                "status": "Considered",
                                "priority": "Medium",
                                "source": "Official career page",
                                "notes": "",
                                "next_action": "Revisit later.",
                                "show_on_dashboard": True,
                                "job_description": "Lead business operations, planning, and executive reporting.",
                            }
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(FollowupGenerationError) as context:
                generate_followups("acme_considered_operations", root)
            bulk = generate_missing_followups(root)

        self.assertIn("considered", str(context.exception).lower())
        self.assertEqual(bulk["generated_count"], 0)
        self.assertEqual(bulk["skipped_existing_count"], 0)
        self.assertEqual(bulk["skipped_count"], 1)

    def test_current_application_statuses_remain_preserved(self):
        tracker_path = PROJECT_ROOT / "data" / "application_tracker.yml"
        before = tracker_path.read_bytes()
        applications = load_application_tracker(PROJECT_ROOT)
        self.assertEqual(tracker_path.read_bytes(), before)
        by_id = {item["id"]: item for item in applications}
        for tracker_id in (
            "playstation_head_global_creative_ops",
            "google_strategy_ops_youtube_auction_brand",
            "paramount_director_marketing_operations",
            "united_talent_agency_director_transformation",
            "disney_entertainment_and_espn_product_technology_director_strategy_operations_product_technology",
            "fieldai_director_of_matrix_operations_organizational_efficiency",
            "bandsintown_senior_copywriter_content_strategist",
        ):
            self.assertIn(get_record_status(by_id[tracker_id]), VALID_STATUSES)
        self.assertIn(
            by_id["playstation_director_ad_ops_invalid"]["status"],
            {"Invalid", "Invalid/Hidden"},
        )
        self.assertEqual(
            get_record_status(by_id["playstation_director_ad_ops_invalid"]),
            "Withdrawn / Closed",
        )
        self.assertFalse(by_id["playstation_director_ad_ops_invalid"]["show_on_dashboard"])


if __name__ == "__main__":
    unittest.main()
