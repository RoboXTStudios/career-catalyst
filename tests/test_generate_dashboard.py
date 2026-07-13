import io
import html
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from scripts.cli import main
from scripts.application_tracker import get_record_status, load_application_tracker
from scripts.generate_dashboard import (
    _asset_label,
    _merge_tracker,
    _package_for_asset,
    _render_badges,
    generate_dashboard,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GenerateDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = generate_dashboard(PROJECT_ROOT)
        cls.output_path = Path(cls.result["output_path"])
        cls.content = cls.output_path.read_text(encoding="utf-8")

    def test_dashboard_is_created_at_expected_path(self):
        expected_path = PROJECT_ROOT / "exports" / "dashboard" / "index.html"
        self.assertEqual(self.output_path, expected_path)
        self.assertTrue(self.output_path.is_file())

    def test_dashboard_is_not_empty(self):
        self.assertGreater(self.output_path.stat().st_size, 0)
        self.assertTrue(self.content.strip())

    def test_dashboard_contains_required_headings(self):
        self.assertIn("Career Catalyst Dashboard", self.content)
        self.assertIn("Applications in Flight", self.content)

    def test_dashboard_contains_signal_first_focus_and_filters(self):
        for heading in (
            "Today’s Focus",
            "Application Summary",
            "Applications in Flight",
            "Application Status",
            "Match Tier",
            "Clear filters",
        ):
            self.assertIn(heading, self.content)
        self.assertNotIn("Recommended Next Steps", self.content)
        self.assertNotIn("Priority Queues", self.content)

    def test_dashboard_cards_include_follow_up_timing_fields(self):
        for label in (
            "Applied",
            "Days since applied",
            "Follow-up",
            "Suggested follow-up",
        ):
            self.assertIn(f"<dt>{label}</dt>", self.content)

    def test_dashboard_contains_generated_file_links(self):
        links = re.findall(r'href="([^"]+)"', self.content)
        self.assertTrue(links)
        for link in links:
            if link.startswith(("http://", "https://")):
                continue
            linked_file = (self.output_path.parent / unquote(link)).resolve()
            self.assertTrue(linked_file.is_file(), f"Missing dashboard target: {link}")

    def test_dashboard_has_no_external_cdn_dependencies(self):
        lowered = self.content.lower()
        self.assertNotIn("cdn", lowered)

    def test_dashboard_uses_relative_file_links(self):
        links = re.findall(r'href="([^"]+)"', self.content)
        for link in links:
            self.assertFalse(link.startswith("/"))
            self.assertFalse(link.startswith("file:"))
        self.assertNotIn(str(PROJECT_ROOT), self.content)

    def test_google_tracker_status_and_notes_apply_to_google_card(self):
        self.assertIn("Google", self.content)
        self.assertIn(
            "Strategy and Operations Lead, YouTube Auction Brand",
            self.content,
        )
        self.assertIn("Official Google Careers", self.content)
        self.assertIn(
            "Submitted application using Google-tailored styled resume and cover letter.",
            self.content,
        )
        self.assertIn('<span class="badge status-applied">Applied</span>', self.content)

    def test_applied_section_preserves_all_applied_roles_without_duplicate_cards(self):
        applications = load_application_tracker(PROJECT_ROOT)
        expected_applied_records = [
            item
            for item in applications
            if get_record_status(item) == "Applied"
        ]
        for item in expected_applied_records:
            self.assertIn(html.escape(str(item["role"])), self.content)
        self.assertEqual(
            self.content.count('data-status="Applied"'),
            len(expected_applied_records),
        )
        role_ids = re.findall(r'id="(role-[^"]+)"', self.content)
        self.assertEqual(len(role_ids), len(set(role_ids)))

    def test_invalid_playstation_role_is_not_in_active_section(self):
        self.assertIn("Director, Ad Operations &amp; Technology", self.content)
        self.assertRegex(
            self.content,
            r'data-status="Withdrawn / Closed"[^>]*>.*?Director, Ad Operations &amp; Technology',
        )
        self.assertIn("closedOnAll", self.content)

    def test_crunchyroll_role_matches_tracker_status(self):
        applications = load_application_tracker(PROJECT_ROOT)
        crunchyroll = next(
            item
            for item in applications
            if item["id"] == "crunchyroll_enterprise_strategy_paused"
        )
        role = "Director, Enterprise Strategy &amp; Initiatives"
        self.assertIn(role, self.content)
        self.assertEqual(get_record_status(crunchyroll), "Withdrawn / Closed")

    def test_dashboard_summary_distinguishes_tracker_states(self):
        for label in (
            "Applied",
            "Under Consideration",
            "Rejected",
            "Withdrawn / Closed",
        ):
            self.assertIn(label, self.content)

    def test_playstation_alias_matching_merges_without_duplicate_card(self):
        package = {
            "company": "Sony Interactive Entertainment / PlayStation",
            "role": "Head of Global Creative and Product Development Operations",
            "tracker": {},
            "files": {},
        }
        packages = [package]
        tracker = [
            {
                "id": "playstation_head_global_creative_ops",
                "company": "  PLAYSTATION ",
                "company_aliases": ["Sony Interactive Entertainment / PlayStation"],
                "role": "Head of Global Creative and Product Development Operations!!!",
                "role_aliases": [
                    "Head Global Creative Product Development Operations"
                ],
                "status": "Applied",
            }
        ]

        _merge_tracker(packages, tracker)

        self.assertEqual(len(packages), 1)
        self.assertEqual(package["tracker"]["status"], "Applied")

    def test_unique_role_fallback_merges_when_company_does_not_match(self):
        package = {
            "company": "Google",
            "role": "Strategy and Operations Lead, YouTube Auction Brand",
            "tracker": {},
            "files": {},
        }
        packages = [package]
        tracker = [
            {
                "company": "Alphabet",
                "role": " strategy and operations lead youtube auction brand ",
                "status": "Applied",
            }
        ]

        _merge_tracker(packages, tracker)

        self.assertEqual(len(packages), 1)
        self.assertEqual(package["tracker"]["status"], "Applied")

    def test_tracker_id_match_has_priority_over_text_fields(self):
        package = {
            "company": "Different Company Label",
            "role": "Different Role Label",
            "tracker_id": "google_strategy_ops_youtube_auction_brand",
            "tracker": {},
            "files": {},
        }
        packages = [package]
        tracker = [
            {
                "id": "google_strategy_ops_youtube_auction_brand",
                "company": "Google",
                "role": "Strategy and Operations Lead, YouTube Auction Brand",
                "status": "Applied",
            }
        ]

        _merge_tracker(packages, tracker)

        self.assertEqual(len(packages), 1)
        self.assertEqual(package["tracker"]["status"], "Applied")

    def test_applied_status_renders_applied_badge(self):
        self.assertEqual(
            _render_badges({"status": "Applied"}),
            '<span class="badge status-applied">Applied</span>',
        )

    def test_dashboard_recognizes_old_and_new_material_filenames(self):
        expected_labels = {
            "exports/messages/Trisha_Lynch_PlayStation_Role_Cover_Letter.md": "Cover Letter",
            "exports/messages/TrishaLynch_HeadGlobalCreativeOps_PlayStation_CoverLetter.md": "Cover Letter",
            "exports/docx/Trisha_Lynch_PlayStation_Resume_Styled.docx": "Styled DOCX",
            "exports/docx/TrishaLynch_HeadGlobalCreativeOps_PlayStation_Styled.docx": "Styled DOCX",
            "exports/strategy_packs/Trisha_Lynch_PlayStation_Role_Strategy_Pack.md": "Strategy Pack",
            "exports/strategy_packs/TrishaLynch_HeadGlobalCreativeOps_PlayStation_StrategyPack.md": "Strategy Pack",
        }
        for path, label in expected_labels.items():
            self.assertEqual(_asset_label(Path(path)), label)

    def test_dashboard_matches_short_and_legacy_names_to_same_package(self):
        package = {
            "company": "Sony Interactive Entertainment / PlayStation",
            "role": "Head of Global Creative and Product Development Operations",
            "tracker": {"status": "Drafted"},
        }
        packages = [package]
        paths = (
            Path(
                "exports/messages/Trisha_Lynch_Sony_Interactive_Entertainment_"
                "PlayStation_Role_Cover_Letter.md"
            ),
            Path(
                "exports/messages/TrishaLynch_HeadGlobalCreativeOps_"
                "PlayStation_CoverLetter.md"
            ),
        )
        for path in paths:
            self.assertIs(_package_for_asset(path, packages), package)

    def test_dashboard_cli_command_succeeds(self):
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = main(["dashboard"])

        self.assertEqual(return_code, 0)
        self.assertIn("Dashboard created", output.getvalue())
        self.assertIn("open exports/dashboard/index.html", output.getvalue())


if __name__ == "__main__":
    unittest.main()
