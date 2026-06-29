import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from scripts.cli import main
from scripts.application_tracker import load_application_tracker
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
        self.assertIn("Application Packages", self.content)

    def test_dashboard_contains_generated_file_links(self):
        links = re.findall(r'href="([^"]+)"', self.content)
        self.assertTrue(links)
        for link in links:
            linked_file = (self.output_path.parent / unquote(link)).resolve()
            self.assertTrue(linked_file.is_file(), f"Missing dashboard target: {link}")

    def test_dashboard_has_no_external_cdn_dependencies(self):
        lowered = self.content.lower()
        self.assertNotIn("https://", lowered)
        self.assertNotIn("http://", lowered)
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

    def test_active_section_preserves_all_applied_roles(self):
        active_section = self.content.split('id="active-applied"', 1)[1].split(
            'id="draft-paused"', 1
        )[0]

        self.assertIn("Strategy and Operations Lead, YouTube Auction Brand", active_section)
        self.assertIn(
            "Head of Global Creative and Product Development Operations",
            active_section,
        )
        self.assertIn("Director, Marketing Operations", active_section)
        applications = load_application_tracker(PROJECT_ROOT)
        expected_applied = sum(
            item["status"] == "Applied" and item.get("show_on_dashboard") is not False
            for item in applications
        )
        self.assertEqual(
            active_section.count('status-applied">Applied</span>'),
            expected_applied,
        )

    def test_invalid_playstation_role_is_not_in_active_section(self):
        active_section = self.content.split('id="active-applied"', 1)[1].split(
            'id="draft-paused"', 1
        )[0]
        hidden_section = self.content.split('id="hidden-invalid-roles"', 1)[1]

        self.assertNotIn("Director, Ad Operations &amp; Technology", active_section)
        self.assertIn("Director, Ad Operations &amp; Technology", hidden_section)
        self.assertIn('status-invalid">Invalid</span>', hidden_section)

    def test_crunchyroll_role_matches_tracker_status(self):
        applications = load_application_tracker(PROJECT_ROOT)
        crunchyroll = next(
            item
            for item in applications
            if item["id"] == "crunchyroll_enterprise_strategy_paused"
        )
        role = "Director, Enterprise Strategy &amp; Initiatives"
        active_section = self.content.split('id="active-applied"', 1)[1].split(
            'id="draft-paused"', 1
        )[0]
        draft_section = self.content.split('id="draft-paused"', 1)[1].split(
            'id="hidden-invalid-roles"', 1
        )[0]
        hidden_section = self.content.split('id="hidden-invalid-roles"', 1)[1]

        if crunchyroll["status"] == "Paused":
            self.assertIn(role, draft_section)
            self.assertIn('status-paused">Paused</span>', draft_section)
        elif crunchyroll["status"] == "Invalid":
            self.assertIn(role, hidden_section)
            self.assertIn('status-invalid">Invalid</span>', hidden_section)
        else:
            self.assertIn(role, self.content)
        self.assertNotIn(role, active_section)

    def test_dashboard_summary_distinguishes_tracker_states(self):
        for label in (
            "Total job files",
            "Active applications",
            "Applied applications",
            "Draft or paused roles",
            "Hidden/invalid roles",
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
