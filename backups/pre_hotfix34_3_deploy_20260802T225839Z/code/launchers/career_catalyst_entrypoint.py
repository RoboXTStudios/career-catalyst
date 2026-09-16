"""Run current Career Catalyst code against an explicitly selected runtime root."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    launcher_root = Path(__file__).resolve().parents[1]
    code_root = Path(
        os.environ.get("CAREER_CATALYST_CODE_ROOT") or launcher_root
    ).expanduser().resolve()
    runtime_root = Path(
        os.environ.get("CAREER_CATALYST_RUNTIME_ROOT") or code_root
    ).expanduser().resolve()
    source = code_root / "app.py"
    if not source.is_file():
        raise RuntimeError(f"Career Catalyst entrypoint not found: {source}")
    if not (runtime_root / "data" / "application_tracker.yml").is_file():
        raise RuntimeError(
            f"Career Catalyst runtime tracker not found beneath: {runtime_root}"
        )

    sys.path.insert(0, str(code_root))
    namespace = {
        "__name__": "__main__",
        "__file__": str(runtime_root / "app.py"),
        "__package__": None,
    }
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        namespace,
    )


if __name__ == "__main__":
    main()
