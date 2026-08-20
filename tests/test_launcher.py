import io
import os
from contextlib import redirect_stdout
from pathlib import Path

from scripts.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_BUNDLE = PROJECT_ROOT / "launchers" / "Career Catalyst.app"
SHELL_LAUNCHER = PROJECT_ROOT / "launchers" / "launch_career_catalyst.sh"
APP_COMMAND = APP_BUNDLE / "Contents" / "Resources" / "launch_career_catalyst.command"


def test_current_launcher_assets_exist_and_are_executable():
    assert APP_BUNDLE.is_dir()
    assert SHELL_LAUNCHER.is_file() and os.access(SHELL_LAUNCHER, os.X_OK)
    assert APP_COMMAND.is_file() and os.access(APP_COMMAND, os.X_OK)


def test_launcher_uses_current_entrypoint_and_durable_runtime_contract():
    content = SHELL_LAUNCHER.read_text(encoding="utf-8")
    assert 'ENTRYPOINT="$CODE_ROOT/launchers/career_catalyst_entrypoint.py"' in content
    assert "launchctl submit" in content
    assert "CAREER_CATALYST_CODE_ROOT" in content
    assert "CAREER_CATALYST_RUNTIME_ROOT" in content
    assert "CAREER_CATALYST_EXPORT_ROOT" in content
    assert "Open_Career_Catalyst.command" not in content


def test_launcher_info_describes_current_app_bundle():
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(["launcher-info"])
    text = output.getvalue()
    assert exit_code == 0
    assert str(APP_BUNDLE) in text
    assert str(SHELL_LAUNCHER) in text
    assert "Double-click Career Catalyst.app" in text
    assert "launchctl-managed" in text
