import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import unquote

from scripts.cli import main
from scripts.generate_dashboard import generate_dashboard


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
        self.assertIn("Sony Interactive Entertainment / PlayStation", self.content)
        self.assertIn(
            "Head of Global Creative and Product Development Operations",
            self.content,
        )
        self.assertIn("Drafted", self.content)

    def test_dashboard_cli_command_succeeds(self):
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = main(["dashboard"])

        self.assertEqual(return_code, 0)
        self.assertIn("Dashboard created", output.getvalue())
        self.assertIn("open exports/dashboard/index.html", output.getvalue())


if __name__ == "__main__":
    unittest.main()
