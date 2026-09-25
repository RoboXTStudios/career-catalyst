"""End-to-end process lifecycle coverage for the macOS launcher."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

# Stand-in for launchctl so the test never registers a real launchd job.
# `submit` starts the command in its own session (detached from the launcher
# wrapper, as launchd would); `remove` stops it. Every call is logged.
FAKE_LAUNCHCTL = """#!/usr/bin/env python3
import os, signal, subprocess, sys
state = os.environ["FAKE_LAUNCHCTL_DIR"]
args = sys.argv[1:]
with open(os.path.join(state, "calls.log"), "a") as log:
    log.write(" ".join(args[:3]) + "\\n")
if args[:1] == ["remove"]:
    pid_file = os.path.join(state, args[1] + ".pid")
    if os.path.exists(pid_file):
        try:
            os.kill(int(open(pid_file).read()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        os.remove(pid_file)
    sys.exit(0)
if args[:1] == ["submit"]:
    label = args[args.index("-l") + 1]
    out = open(args[args.index("-o") + 1], "a")
    err = open(args[args.index("-e") + 1], "a")
    command = args[args.index("--") + 1:]
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
    with open(os.path.join(state, label + ".pid"), "w") as handle:
        handle.write(str(proc.pid))
    sys.exit(0)
sys.stderr.write("fake launchctl: unsupported call %r\\n" % (args,))
sys.exit(2)
"""


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "launchers" / "launch_career_catalyst.sh"


def test_launcher_uses_launchd_and_explicit_runtime_contract():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "launchctl submit" in source
    assert "nohup" not in source
    assert 'DEFAULT_PYTHON_BIN="$STATE_DIR/venv/bin/python"' in source
    assert 'export CAREER_CATALYST_CODE_ROOT="$1"' in source
    assert 'export CAREER_CATALYST_RUNTIME_ROOT="$2"' in source
    assert 'export CAREER_CATALYST_EXPORT_ROOT="$3"' in source
    assert 'pid="$(listener_pid "$port")"' in source


def _free_port() -> int:
    # Scan down from the top of the launcher's range so the test never takes
    # the app's real ports (8503, and 8504 when 8503 is busy).
    for port in range(8599, 8549, -1):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free Career Catalyst test port")


def _wait_for(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return False


def _listener_pid(port: int) -> int | None:
    result = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.strip().isdigit():
            return int(line.strip())
    return None


def _health(port: int) -> bool:
    result = subprocess.run(
        ["curl", "-fsS", "--max-time", "2", f"http://127.0.0.1:{port}/_stcore/health"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "ok"


def test_launcher_pid_survives_wrapper_exit_and_reuses_existing_process(tmp_path):
    """The actual launcher must hand ownership to launchctl, not its shell."""

    code_root = tmp_path / "code"
    runtime_root = tmp_path / "runtime"
    state_root = tmp_path / "state"
    log_root = tmp_path / "logs"
    export_root = tmp_path / "exports"
    (code_root / "launchers").mkdir(parents=True)
    (runtime_root / "data").mkdir(parents=True)
    (runtime_root / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    shutil.copy2(
        PROJECT_ROOT / "launchers" / "career_catalyst_entrypoint.py",
        code_root / "launchers" / "career_catalyst_entrypoint.py",
    )
    (code_root / "app.py").write_text(
        "import streamlit as st\n"
        "st.write('launcher lifecycle fixture')\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_state = tmp_path / "launchctl"
    fake_bin.mkdir()
    fake_state.mkdir()
    fake_launchctl = fake_bin / "launchctl"
    fake_launchctl.write_text(FAKE_LAUNCHCTL, encoding="utf-8")
    fake_launchctl.chmod(0o755)

    port = _free_port()
    job_label = f"com.roboxtstudios.careercatalyst.{port}"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "FAKE_LAUNCHCTL_DIR": str(fake_state),
        "CAREER_CATALYST_STATE_DIR": str(state_root),
        "CAREER_CATALYST_LOG_DIR": str(log_root),
        "CAREER_CATALYST_CODE_ROOT": str(code_root),
        "CAREER_CATALYST_RUNTIME_ROOT": str(runtime_root),
        "CAREER_CATALYST_EXPORT_ROOT": str(export_root),
        "CAREER_CATALYST_BASE_PORT": str(port),
        "CAREER_CATALYST_PYTHON": os.environ.get("PYTHON", os.sys.executable),
        "CAREER_CATALYST_OPEN_COMMAND": "/usr/bin/true",
    }
    stale_state = state_root / "runtime.state"
    state_root.mkdir(parents=True)
    stale_state.write_text(
        "pid=76831\nport=8503\ncode_root=/stale\nentrypoint=/stale/entrypoint.py\n",
        encoding="utf-8",
    )

    persistent_pid = None
    try:
        # subprocess.run returns only after the launching wrapper has exited.
        result = subprocess.run(
            ["/bin/bash", str(LAUNCHER)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        assert result.stderr == ""
        state = {
            line.split("=", 1)[0]: line.split("=", 1)[1]
            for line in stale_state.read_text(encoding="utf-8").splitlines()
            if "=" in line
        }
        persistent_pid = int(state["pid"])
        assert persistent_pid != 76831
        assert state["port"] == str(port)
        assert state["job_label"] == f"com.roboxtstudios.careercatalyst.{port}"
        assert _listener_pid(port) == persistent_pid
        assert _health(port)

        # The launch wrapper is gone; wait the full acceptance interval before
        # asserting that launchd, rather than the wrapper, owns the process.
        time.sleep(60)
        assert _listener_pid(port) == persistent_pid
        assert _health(port)
        root = subprocess.run(
            ["curl", "-fsS", "--max-time", "2", f"http://127.0.0.1:{port}/"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert root.returncode == 0
        assert '<div id="root"></div>' in root.stdout

        second = subprocess.run(
            ["/bin/bash", str(LAUNCHER)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        assert second.stderr == ""
        assert int(
            next(
                line.split("=", 1)[1]
                for line in stale_state.read_text(encoding="utf-8").splitlines()
                if line.startswith("pid=")
            )
        ) == persistent_pid
        assert _listener_pid(port) == persistent_pid
    finally:
        if persistent_pid:
            try:
                os.kill(persistent_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            _wait_for(lambda: _listener_pid(port) is None, timeout=10)
        subprocess.run([str(fake_launchctl), "remove", job_label], env=env, check=False)
        # Read-only check against the real launchd: nothing may be registered.
        if shutil.which("launchctl"):
            real = subprocess.run(["launchctl", "list", job_label], capture_output=True, check=False)
            assert real.returncode != 0, f"test leaked a real launchd job: {job_label}"

    calls = (fake_state / "calls.log").read_text(encoding="utf-8").splitlines()
    assert f"submit -l {job_label}" in calls
