import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import app
from scripts.application_tracker import add_prospect, load_application_tracker
from scripts.filename_utils import (
    build_upload_filename,
    company_display_name,
    short_company_name,
)
from scripts.generate_cover_letter import generate_cover_letter
from scripts.generate_dashboard import _render_html, _render_package
from scripts.generate_messages import generate_message
from scripts.job_freshness import detect_job_freshness
from tests.test_sprint15_4 import _FakeStreamlit, _record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = PROJECT_ROOT / "tests/fixtures/cover_letters/golden/umg_project_pmo_user_edited.txt"
ANTI_PATTERN = PROJECT_ROOT / "tests/fixtures/cover_letters/anti_patterns/umg_project_pmo_generated_redundant.txt"


class CoverLetterVoiceAndCompanyTests(unittest.TestCase):
    def test_golden_and_anti_pattern_fixtures_capture_the_edit(self):
        golden = GOLDEN.read_text(encoding="utf-8")
        anti = ANTI_PATTERN.read_text(encoding="utf-8")
        self.assertIn("Universal Music Group", golden)
        self.assertNotIn("600 UMG Recordings Inc", golden)
        self.assertIn("600 UMG Recordings Inc", anti)
        self.assertIn("practical operating style", anti)
        self.assertNotIn("practical operating style", golden)

    def test_company_display_names_and_material_filenames_are_human(self):
        expected = {
            "600 UMG Recordings Inc": "Universal Music Group",
            "Universal Music Group (UMG Recordings Inc.)": "Universal Music Group",
            "Paramount Streaming LLC": "Paramount",
            "AEG Worldwide/AXS": "AEG/AXS",
            "Warner Chappell Music Inc": "WMG",
        }
        for raw, display in expected.items():
            self.assertEqual(company_display_name(raw), display)
        self.assertEqual(short_company_name("600 UMG Recordings Inc"), "UMG")
        filename = build_upload_filename(
            "Trisha Lynch",
            "Senior Director, Project and PMO Lead",
            "600 UMG Recordings Inc",
            "Cover Letter",
            "txt",
        )
        self.assertIn("_UMG_", filename)
        self.assertNotIn("600UmgRecordings", filename)

    def test_generated_umg_letter_and_message_use_cleaner_four_paragraph_voice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ("data", "config"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            (root / "jobs").mkdir()
            job = root / "jobs" / "umg_project_pmo.md"
            job.write_text(
                "# Senior Director, Project and PMO Lead\n\n"
                "Company: 600 UMG Recordings Inc\n\n"
                "## Job Description\n\n"
                "Lead project management, PMO governance, technical and creative delivery, "
                "roadmaps, dependencies, quality assurance, reporting, risk management, and "
                "cross-functional stakeholder alignment across a global music organization.",
                encoding="utf-8",
            )
            letter_result = generate_cover_letter("jobs/umg_project_pmo.md", root)
            recruiter_result = generate_message("recruiter", "jobs/umg_project_pmo.md", root)
            letter = Path(letter_result["output_path"]).read_text(encoding="utf-8")
            recruiter = Path(recruiter_result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("Universal Music Group", letter)
            self.assertIn("Universal Music Group", recruiter)
            self.assertNotIn("600 UMG Recordings", letter + recruiter)
            self.assertNotIn("is compelling because it sits", letter)
            self.assertNotIn("practical operating style", letter)
            body = [
                paragraph.strip()
                for paragraph in letter.split("\n\n")
                if paragraph.strip() not in {"Hello,", "Best,", "Trisha Lynch"}
            ]
            self.assertEqual(len(body), 4)

    def test_static_dashboard_uses_display_company_without_changing_raw_package(self):
        package = {
            "company": "600 UMG Recordings Inc",
            "role": "Senior Director, Project and PMO Lead",
            "tracker": {},
            "files": {},
        }
        rendered = _render_package(package, Path("/tmp"))
        self.assertIn("Universal Music Group", rendered)
        self.assertNotIn("600 UMG Recordings Inc", rendered)
        self.assertEqual(package["company"], "600 UMG Recordings Inc")


class PostingDateAndVerificationTests(unittest.TestCase):
    def test_posting_date_detection_handles_schema_relative_standard_and_unknown(self):
        today = date(2026, 7, 7)
        cases = {
            '"datePosted": "2026-07-03"': "2026-07-03",
            "Posted today": "2026-07-07",
            "Posted yesterday": "2026-07-06",
            "Posted 5 days ago": "2026-07-02",
            "Posting date: 06/30/2026": "2026-06-30",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(
                    detect_job_freshness(text, today)["posting_date"], expected
                )
        unknown = detect_job_freshness("No posting date shown", today)
        self.assertIsNone(unknown["posting_date"])
        self.assertEqual(unknown["posting_date_label"], "Posting date unknown")

    def test_verify_navigation_focuses_role_and_opens_source_panel(self):
        state = {"dashboard_compact_mode": True}
        app.focus_source_verification(state, "stable-role")
        self.assertEqual(state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(
            state["dashboard_source_verification_role_id"], "stable-role"
        )

    def test_manual_source_fields_persist_through_canonical_update_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "data" / "application_tracker.yml").write_text(
                "applications: []\n", encoding="utf-8"
            )
            add_prospect(
                {
                    "id": "umg-pmo",
                    "company": "600 UMG Recordings Inc",
                    "role": "Senior Director, Project and PMO Lead",
                    "status": "Active",
                    "priority": "High",
                    "show_on_dashboard": True,
                },
                root,
            )
            app.update_dashboard_role(
                "umg-pmo",
                {
                    "status": "Active",
                    "posting_date": "2026-07-07",
                    "verification_status": "Verified Active",
                    "source_verified": True,
                    "freshness": "Fresh",
                    "verification_notes": "Confirmed on employer site.",
                },
                root,
            )
            saved = load_application_tracker(root)[0]
            self.assertEqual(saved["posting_date"], "2026-07-07")
            self.assertEqual(saved["verification_status"], "Verified Active")
            self.assertTrue(saved["source_verified"])
            self.assertEqual(saved["freshness"], "Fresh")
            self.assertEqual(
                saved["verification_notes"], "Confirmed on employer site."
            )


class CompactDashboardTests(unittest.TestCase):
    def test_compact_role_card_only_navigates_to_focused_workspace(self):
        record = _record()
        st = _FakeStreamlit(clicks={"compact_view_stable-role"})
        app._render_role_card(st, record, {}, compact=True)
        self.assertEqual(st.session_state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(st.reruns, 1)


    def test_static_dashboard_renders_compact_command_center_cards(self):
        package = {
            "company": "Acme Inc",
            "role": "Director of Operations",
            "tracker": {
                "id": "acme-director-ops",
                "status": "Applied",
                "follow_up_status": "Due now",
                "match_score": 88,
                "match_tier": "Strong Match",
                "recommended_action": "Follow Up",
                "source_trust_label": "Verified Company Source",
                "verification_status": "Employer Source",
                "match_strengths": ["Operations leadership"],
                "verification_notes": "Confirmed on employer site.",
                "original_source_url": "https://example.com/job",
            },
            "files": {},
        }
        rendered = _render_package(package, Path("/tmp"))
        self.assertIn('class="application-card compact-role-card"', rendered)
        self.assertIn('id="role-acme-director-ops"', rendered)
        self.assertIn("View Role", rendered)
        self.assertIn("Open Posting", rendered)
        self.assertIn('href="https://example.com/job"', rendered)
        self.assertIn("Open Materials", rendered)
        self.assertIn('<details class="role-details">', rendered)
        self.assertNotIn('<details class="role-details" open', rendered)
        self.assertIn('class="match-details"', rendered)
        self.assertIn("Verification Status", rendered)

    def test_static_dashboard_next_steps_and_controls_are_compact(self):
        package = {
            "company": "Acme Inc",
            "role": "Director of Operations",
            "tracker": {
                "id": "acme-director-ops",
                "status": "Applied",
                "follow_up_status": "Due now",
                "match_score": 88,
                "match_tier": "Strong Match",
                "recommended_action": "Follow Up",
                "source_trust_label": "Verified Company Source",
                "verification_status": "Employer Source",
                "original_source_url": "https://example.com/job",
            },
            "files": {},
        }
        groups = {"active": [], "applied": [package], "reviewed": [], "paused": [], "pass": [], "hidden": []}
        counts = {"Total": 1, "Active": 0, "Applied / Follow-up": 1, "Reviewed": 0, "Paused": 0, "Pass": 0, "Hidden / Invalid": 0}
        content = _render_html(groups, counts, [], Path("/tmp/dashboard"))
        self.assertIn('class="recommended-steps compact-next-steps"', content)
        self.assertIn('class="next-step-row"', content)
        self.assertIn('data-collapse-all', content)
        self.assertIn('data-focus-role="role-acme-director-ops"', content)
        self.assertEqual(content.count('id="role-acme-director-ops"'), 1)
        self.assertEqual(content.count('data-role-anchor="role-acme-director-ops"'), 1)
        self.assertIn("Source Type", content)
        self.assertIn("Verification Status", content)
        self.assertIn("Sort by", __import__("inspect").getsource(app._render_dashboard))

    def test_dashboard_exposes_requested_workspace_controls(self):
        source = __import__("inspect").getsource(app._render_dashboard)
        for label in ("Collapse All", "Expand Focused", "Clear Focus"):
            self.assertIn(label, source)

    def test_source_verification_panel_exposes_all_manual_fields(self):
        inspect = __import__("inspect")
        source = inspect.getsource(app._render_role_card) + inspect.getsource(
            app._render_source_verification_panel
        )
        for label in (
            "Source Verification",
            "Posting date",
            "Verified status",
            "Source verified",
            "Freshness",
            "Verification notes",
            "Save source verification",
        ):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
