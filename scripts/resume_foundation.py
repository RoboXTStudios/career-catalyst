"""Explicit canonical résumé foundation for all tailoring workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

try:
    from .load_data import DataLoadError, load_all_yaml
except ImportError:
    from load_data import DataLoadError, load_all_yaml


PathInput = Optional[Union[str, Path]]
DEFAULT_BASELINE_FILES = (
    "data/positions.yml",
    "data/achievements.yml",
    "data/skills.yml",
    "data/platforms.yml",
    "data/projects.yml",
    "data/certifications.yml",
    "data/personal_brand.yml",
)


def _foundation_info(root: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    settings = loaded["config"].get("settings", {})
    configured = settings.get("canonical_resume_foundation") or {}
    files = tuple(configured.get("baseline_files") or DEFAULT_BASELINE_FILES)
    missing = [relative for relative in files if not (root / relative).is_file()]
    if missing:
        raise DataLoadError(
            "Canonical résumé foundation is incomplete: " + ", ".join(missing)
        )
    return {
        "name": str(configured.get("name") or "Career Catalyst structured career dataset"),
        "kind": str(configured.get("kind") or "structured_yaml"),
        "baseline_files": files,
        "supplemental_evidence_source": str(
            configured.get("supplemental_evidence_source") or "data/evidence_projects.yml"
        ),
        "last_updated": str(configured.get("last_updated") or "Unknown"),
        "last_verified": str(configured.get("last_verified") or "Unknown"),
    }


def canonical_resume_foundation_info(project_root: PathInput = None) -> dict[str, Any]:
    """Return the configured foundation identity without reading generated résumés."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    return _foundation_info(root, load_all_yaml(root))


def load_resume_foundation(project_root: PathInput = None) -> dict[str, Any]:
    """Load the one immutable-at-generation baseline used by résumé and letter tailoring."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    loaded = load_all_yaml(root)
    _foundation_info(root, loaded)
    return loaded
