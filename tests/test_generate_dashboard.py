import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from scripts.cli import main
from scripts.generate_dashboard import _asset_label, _package_for_asset, generate_dashboard
from scripts.load_data import load_yaml_file


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

    def test_dashboard_contains_playstation_tracker_package(self):
        tracker = load_yaml_file("data/application_tracker.yml", PROJECT_ROOT)
        playstation_status = tracker["applications"][0]["status"]

        self.assertIn("Sony Interactive Entertainment / PlayStation", self.content)
        self.assertIn(
            "Head of Global Creative and Product Development Operations",
            self.content,
        )
        self.assertIn(playstation_status, self.content)

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
