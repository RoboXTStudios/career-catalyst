"""Static launcher contract checks for Sprint 40."""

from pathlib import Path


def test_launcher_defaults_to_durable_venv_and_validates_pid_after_health():
    source = Path("launchers/launch_career_catalyst.sh").read_text(encoding="utf-8")
    assert 'DEFAULT_PYTHON_BIN="$STATE_DIR/venv/bin/python"' in source
    assert 'kill -0 "$pid"' in source
    assert "stopped immediately after becoming healthy" in source
    assert "127.0.0.1" in source
    assert "8501" not in source
