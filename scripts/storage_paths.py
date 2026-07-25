"""Resolve stable Career Catalyst storage independently of the active worktree."""

from __future__ import annotations

import os
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Union

import yaml


PathInput = Union[str, Path]
EXPORT_ROOT_ENV = "CAREER_CATALYST_EXPORT_ROOT"


class StoragePathError(ValueError):
    """Raised when a production package path escapes the configured library."""


def _repository_main_root(project_root: Path) -> Path:
    """Return the primary checkout root for a normal checkout or linked worktree."""
    marker = project_root / ".git"
    if marker.is_dir():
        return project_root.resolve()
    if marker.is_file():
        first_line = marker.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        if first_line.lower().startswith("gitdir:"):
            git_dir = Path(first_line.split(":", 1)[1].strip()).expanduser()
            if not git_dir.is_absolute():
                git_dir = (project_root / git_dir).resolve()
            # Linked worktrees live at <main>/.git/worktrees/<name>.
            if git_dir.parent.name == "worktrees":
                return git_dir.parent.parent.parent.resolve()
    return project_root.resolve()


def canonical_export_root(
    project_root: Optional[PathInput] = None,
    *,
    injected_root: Optional[PathInput] = None,
) -> Path:
    """Return the explicit package library root.

    Tests pass ``injected_root``. Production may use the environment override;
    otherwise ``config/settings.yml`` selects the repository-main convention.
    This never depends on the process working directory when ``project_root`` is
    supplied by the application.
    """
    root = Path(project_root or Path.cwd()).expanduser().resolve()
    if injected_root is not None:
        return Path(injected_root).expanduser().resolve()
    configured_env = str(os.environ.get(EXPORT_ROOT_ENV) or "").strip()
    if configured_env:
        return Path(configured_env).expanduser().resolve()
    if os.environ.get("PYTEST_CURRENT_TEST") and (root / ".git").exists():
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
        return (Path(tempfile.gettempdir()) / "career-catalyst-test-exports" / digest).resolve()

    convention = "repository_main/exports"
    settings_path = root / "config" / "settings.yml"
    if settings_path.is_file():
        loaded = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        convention = str((loaded.get("paths") or {}).get("canonical_exports") or convention)
    if convention == "repository_main/exports":
        return (_repository_main_root(root) / "exports").resolve()
    configured = Path(convention).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    raise StoragePathError(
        "paths.canonical_exports must be an absolute path or 'repository_main/exports'."
    )


def require_beneath_export_root(path: PathInput, export_root: PathInput) -> Path:
    """Resolve and validate a production output beneath its canonical root."""
    resolved = Path(path).expanduser().resolve()
    root = Path(export_root).expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise StoragePathError(
            f"Package path '{resolved}' is outside canonical export root '{root}'."
        )
    return resolved


def legacy_material_paths(application: dict, export_root: PathInput) -> list[str]:
    """Report stored material/manifest paths outside the canonical root read-only."""
    def generated_values(mapping: dict) -> list[object]:
        excluded = {"job description", "job file", "source", "source file", "dashboard"}
        return [
            value
            for label, value in dict(mapping or {}).items()
            if str(label).strip().lower().replace("_", " ") not in excluded
        ]

    values = generated_values(application.get("material_paths") or {})
    manifest = application.get("package_manifest")
    if isinstance(manifest, dict):
        values.extend(generated_values(manifest.get("materials") or {}))
        values.extend(generated_values(manifest.get("files") or {}))
        values.append(manifest.get("manifest_path"))
    root = Path(export_root).expanduser().resolve()
    stranded = []
    for value in values:
        if not value:
            continue
        resolved = Path(str(value)).expanduser().resolve()
        if resolved != root and root not in resolved.parents:
            stranded.append(str(resolved))
    return list(dict.fromkeys(stranded))
