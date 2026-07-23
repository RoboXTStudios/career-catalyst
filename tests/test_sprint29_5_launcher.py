import os
import plistlib
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "launchers" / "launch_career_catalyst.sh"
ENTRYPOINT = PROJECT_ROOT / "launchers" / "career_catalyst_entrypoint.py"
APP_ROOT = PROJECT_ROOT / "launchers" / "Career Catalyst.app"


def _source_and_run(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "CAREER_CATALYST_SOURCE_ONLY": "1",
        "CAREER_CATALYST_STATE_DIR": str(tmp_path / "state"),
        "CAREER_CATALYST_LOG_DIR": str(tmp_path / "logs"),
        "CAREER_CATALYST_CODE_ROOT": str(PROJECT_ROOT),
        "CAREER_CATALYST_RUNTIME_ROOT": str(PROJECT_ROOT),
        "CAREER_CATALYST_EXPORT_ROOT": str(tmp_path / "exports"),
    }
    return subprocess.run(
        ["/bin/bash", "-c", f'source "$1"\n{script}', "launcher-test", str(LAUNCHER)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_launcher_shell_and_app_bundle_are_valid():
    subprocess.run(["/bin/bash", "-n", str(LAUNCHER)], check=True)
    subprocess.run(
        ["/bin/bash", "-n", str(APP_ROOT / "Contents" / "MacOS" / "Career Catalyst")],
        check=True,
    )
    with (APP_ROOT / "Contents" / "Info.plist").open("rb") as handle:
        plist = plistlib.load(handle)
    assert plist["CFBundleIdentifier"] == "com.roboxtstudios.careercatalyst"
    assert plist["CFBundleExecutable"] == "Career Catalyst"


def test_entrypoint_uses_current_code_with_the_selected_runtime(tmp_path):
    code_root = tmp_path / "code"
    runtime_root = tmp_path / "runtime"
    (code_root / "launchers").mkdir(parents=True)
    (runtime_root / "data").mkdir(parents=True)
    (runtime_root / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    (code_root / "app.py").write_text(
        "print('runtime_file=' + __file__)\n", encoding="utf-8"
    )
    result = subprocess.run(
        ["python3", str(ENTRYPOINT)],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CAREER_CATALYST_CODE_ROOT": str(code_root),
            "CAREER_CATALYST_RUNTIME_ROOT": str(runtime_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert result.stdout.strip() == f"runtime_file={runtime_root / 'app.py'}"


def test_correct_career_catalyst_on_8503_is_reused(tmp_path):
    result = _source_and_run(
        """
listener_pid() { [ "$1" = "8503" ] && printf '123\\n'; }
is_career_catalyst_process() { [ "$1" = "123" ] && [ "$2" = "8503" ]; }
choose_target
""",
        tmp_path,
    )
    assert result.stdout.strip() == "reuse:8503:123"


def test_unrelated_8503_process_is_not_stopped_and_next_port_is_used(tmp_path):
    result = _source_and_run(
        """
listener_pid() {
  if [ "$1" = "8503" ]; then printf '999\\n'; fi
}
is_career_catalyst_process() { return 1; }
choose_target
""",
        tmp_path,
    )
    assert result.stdout.strip() == "start:8504:"


def test_manifest_write_paths_are_outside_the_repository():
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "Library/Logs/Career Catalyst" in text
    assert "Library/Application Support/Career Catalyst" in text
    assert 'kill -0 "$pid"' in text
    assert "kill -9" not in text
    assert "kill \"$pid\"" not in text
