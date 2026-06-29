import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = PROJECT_ROOT / "launchers" / "Open_Career_Catalyst.command"


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = LAUNCHER_PATH.read_text(encoding="utf-8")

    def test_launcher_exists(self):
        self.assertTrue(LAUNCHER_PATH.is_file())

    def test_launcher_runs_streamlit_app(self):
        self.assertIn("python3 -m streamlit run app.py", self.content)

    def test_launcher_resolves_project_root_relative_to_itself(self):
        self.assertIn('SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"', self.content)
        self.assertIn('PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"', self.content)
        self.assertIn('cd "$PROJECT_ROOT"', self.content)
        self.assertNotIn(str(PROJECT_ROOT), self.content)

    def test_launcher_is_executable(self):
        self.assertTrue(os.access(LAUNCHER_PATH, os.X_OK))

    def test_launcher_info_command_works(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["launcher-info"])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(str(LAUNCHER_PATH), text)
        self.assertIn("chmod +x launchers/Open_Career_Catalyst.command", text)
        self.assertIn("Double-click", text)
        self.assertIn("Control+C", text)


if __name__ == "__main__":
    unittest.main()
