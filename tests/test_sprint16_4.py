import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from scripts.generate_dashboard import _attach_assets, _merge_tracker
from scripts.generate_cover_letter import save_material
from scripts.package_context import (
    CONTEXT_MISMATCH_MESSAGE,
    PackageContextMismatchError,
    validate_material_context,
)
from scripts.package_generator import PackageGenerationError, build_package_context
from scripts.package_materials import validate_package_outputs
from tests.test_sprint15_4 import _FakeStreamlit, _record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "package_context_bleed"


class PackageContextIsolationTests(unittest.TestCase):
    def test_google_bleed_fixtures_are_blocked_for_netflix(self):
        parsed_job = {
            "company": "Netflix",
            "job_title": "Program Manager, Design",
            "raw_text": "Lead design programs, creative workflows, and cross-functional delivery.",
        }
        for fixture in sorted(FIXTURES.glob("*.txt")):
            with self.subTest(fixture=fixture.name):
                with self.assertRaisesRegex(
                    PackageContextMismatchError, CONTEXT_MISMATCH_MESSAGE
                ):
                    validate_material_context(
                        fixture.read_text(encoding="utf-8"), parsed_job, fixture.stem
                    )

    def test_target_company_and_job_authorized_language_are_allowed(self):
        netflix = {
            "company": "Netflix",
            "job_title": "Program Manager, Design",
            "raw_text": "This role partners on YouTube product activation and seller enablement.",
        }
        result = validate_material_context(
            "Netflix needs thoughtful YouTube product activation and seller enablement.",
            netflix,
        )
        self.assertTrue(result["valid"])

        google = {
            "company": "Google",
            "job_title": "Strategy and Operations Lead",
            "raw_text": "YouTube Brand Auction and seller enablement.",
        }
        self.assertTrue(
            validate_material_context("This Google opportunity includes YouTube Brand Auction.", google)[
                "valid"
            ]
        )

    def test_file_name_is_not_trusted_as_content_proof(self):
        fixture = FIXTURES / "netflix_program_manager_design_recruiter_google_bleed.txt"
        self.assertIn("netflix", fixture.name)
        with self.assertRaises(PackageContextMismatchError):
            validate_material_context(
                fixture.read_text(encoding="utf-8"),
                {"company": "Netflix", "raw_text": "Design program management."},
            )

    def test_contaminated_material_is_blocked_before_overwriting_valid_file(self):
        fixture = FIXTURES / "netflix_program_manager_design_application_note_google_bleed.txt"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = {
                "root": root,
                "voice": {"avoid": []},
                "parsed_job": {
                    "company": "Netflix",
                    "job_title": "Program Manager, Design",
                    "raw_text": "Lead design programs and creative workflows.",
                },
                "career_data": {
                    "data": {"personal_brand": {"candidate": {"name": "Trisha Lynch"}}}
                },
                "match_report": {"match_score": 80},
            }
            valid = save_material(
                context,
                "Application_Note",
                "Netflix design program leadership needs clear creative workflows and dependable delivery.",
                minimum_words=1,
                maximum_words=100,
            )
            output_path = Path(valid["output_path"])
            original = output_path.read_text(encoding="utf-8")
            with self.assertRaises(PackageContextMismatchError):
                save_material(
                    context,
                    "Application_Note",
                    fixture.read_text(encoding="utf-8"),
                    minimum_words=1,
                    maximum_words=200,
                )
            self.assertEqual(output_path.read_text(encoding="utf-8"), original)

    def test_build_package_context_uses_only_exact_selected_prospect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "jobs").mkdir()
            netflix_job = root / "jobs" / "netflix.md"
            google_job = root / "jobs" / "google.md"
            netflix_job.write_text(
                "# Program Manager, Design\n\nCompany: Netflix\n\nTracker ID: netflix-role\n\n"
                "## Job Description\n\nLead design programs and creative workflows.",
                encoding="utf-8",
            )
            google_job.write_text(
                "# Strategy and Operations Lead\n\nCompany: Google\n\nTracker ID: google-role\n\n"
                "## Job Description\n\nLead YouTube product activation and seller enablement.",
                encoding="utf-8",
            )
            tracker = [
                {
                    "id": "google-role",
                    "company": "Google",
                    "role": "Strategy and Operations Lead",
                    "job_file": "jobs/google.md",
                    "material_paths": {"Recruiter Message": "google.txt"},
                },
                {
                    "id": "netflix-role",
                    "company": "Netflix",
                    "role": "Program Manager, Design",
                    "job_file": "jobs/netflix.md",
                    "material_paths": {"Recruiter Message": "netflix.txt"},
                },
            ]

            def intelligence(**values):
                return {
                    "company": values["company_name"],
                    "role": values["job_title"],
                    "description": values["job_description"],
                }

            with patch(
                "scripts.package_generator.get_effective_voice_profile",
                side_effect=intelligence,
            ), patch(
                "scripts.package_generator.score_job_match",
                return_value={"match_score": 80},
            ):
                google = build_package_context("google-role", tracker, root)
                netflix = build_package_context("netflix-role", tracker, root)
                google_again = build_package_context("google-role", tracker, root)

            self.assertEqual(netflix["prospect_id"], "netflix-role")
            self.assertEqual(netflix["company"], "Netflix")
            self.assertEqual(netflix["role_title"], "Program Manager, Design")
            self.assertNotIn("YouTube", netflix["job_description"])
            self.assertEqual(
                netflix["selected_package_paths"],
                {"Recruiter Message": "netflix.txt"},
            )
            self.assertIn("YouTube", google["role_intelligence"]["description"])
            self.assertNotIn("Netflix", google_again["role_intelligence"]["description"])

    def test_selection_change_resets_stale_package_preview(self):
        state = {
            "package_preview_prospect_id": "google-role",
            "last_package_outputs": {"recruiter": "google.md"},
            "last_package_result": {"tracker_id": "google-role"},
        }
        self.assertTrue(app.reset_package_preview_for_selection(state, "netflix-role"))
        self.assertNotIn("last_package_outputs", state)
        self.assertNotIn("last_package_result", state)
        self.assertEqual(state["package_preview_prospect_id"], "netflix-role")

    def test_exact_record_rejects_job_file_with_different_company(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "jobs").mkdir()
            (root / "jobs" / "wrong.md").write_text(
                "# Program Manager, Design\n\nCompany: Google\n\n"
                "## Job Description\n\nLead design programs and creative workflows.",
                encoding="utf-8",
            )
            tracker = [
                {
                    "id": "netflix-role",
                    "company": "Netflix",
                    "role": "Program Manager, Design",
                    "job_file": "jobs/wrong.md",
                }
            ]
            with self.assertRaisesRegex(
                PackageGenerationError, "Package context mismatch detected"
            ):
                build_package_context("netflix-role", tracker, root)


class ExactMaterialManifestTests(unittest.TestCase):
    def test_exact_tracker_manifest_wins_and_fuzzy_asset_is_unassigned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            messages = root / "exports" / "messages"
            messages.mkdir(parents=True)
            exact = root / "exact_netflix.txt"
            fuzzy = messages / "TrishaLynch_ProgramManagerDesign_Netflix_RecruiterMessage.txt"
            exact.write_text("exact", encoding="utf-8")
            fuzzy.write_text("wrong", encoding="utf-8")
            package = {
                "company": "Netflix",
                "role": "Program Manager, Design",
                "tracker_id": "netflix-role",
                "tracker": {},
                "files": {},
            }
            tracker = [
                {
                    "id": "netflix-role",
                    "company": "Netflix",
                    "role": "Program Manager, Design",
                    "material_paths": {"Recruiter Message": str(exact)},
                }
            ]
            _merge_tracker([package], tracker, root)
            with patch(
                "scripts.generate_dashboard.ASSET_DIRECTORIES", ("exports/messages",)
            ):
                unassigned = _attach_assets(root, [package])
            self.assertEqual(
                package["files"]["Recruiter Message"].resolve(), exact.resolve()
            )
            self.assertIn(("Recruiter Message", fuzzy), unassigned)

    def test_blocked_material_has_explicit_checklist_state(self):
        checklist = validate_package_outputs(
            {}, {"application_note": "Blocked: package context mismatch"}
        )
        note = next(item for item in checklist if item["material_type"] == "Application Note")
        self.assertFalse(note["exists"])
        self.assertEqual(note["missing_reason"], "Blocked: package context mismatch")


class DashboardNavigationPolishTests(unittest.TestCase):
    def test_collapse_all_collapses_next_steps_without_changing_filters(self):
        state = {
            "dashboard_mode": "Follow-Up Mode",
            "dashboard_search": "Netflix",
            "dashboard_sort": "Match score",
        }
        app.collapse_dashboard_working_view(state)
        self.assertTrue(state["dashboard_compact_mode"])
        self.assertTrue(state["dashboard_next_steps_collapsed"])
        self.assertEqual(state["dashboard_mode"], "Follow-Up Mode")
        self.assertEqual(state["dashboard_search"], "Netflix")

    def test_collapsed_next_steps_render_header_and_expand_only(self):
        st = _FakeStreamlit(
            state={
                "dashboard_compact_mode": True,
                "dashboard_next_steps_collapsed": True,
            }
        )
        app._render_recommended_next_steps(st, [_record()], "All Mode", {})
        self.assertEqual({label for label, _ in st.buttons}, {"Expand"})
        rendered = "\n".join(value for kind, value in st.messages if kind == "markdown")
        self.assertIn("Recommended Next Steps (1)", rendered)
        self.assertNotIn("Director, Operations", rendered)

    def test_view_role_renders_focused_workspace_directly_below_next_steps(self):
        record = _record()
        st = _FakeStreamlit(clicks={"next_view_stable-role"})
        with patch.object(app, "_render_role_card") as render_role:
            focused_id = app._render_recommended_next_steps(
                st, [record], "All Mode", {}, focus_records=[record]
            )
        self.assertEqual(focused_id, "stable-role")
        self.assertEqual(st.session_state["dashboard_focused_role_id"], "stable-role")
        self.assertTrue(
            any("Focused Role Workspace" in value for _, value in st.messages)
        )
        render_role.assert_called_once()

    def test_verify_manual_focus_helper_still_opens_source_verification(self):
        state = {"dashboard_compact_mode": True}
        app.focus_source_verification(state, "stable-role")
        self.assertEqual(state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(state["dashboard_source_verification_role_id"], "stable-role")
        self.assertFalse(state["dashboard_compact_mode"])


if __name__ == "__main__":
    unittest.main()
