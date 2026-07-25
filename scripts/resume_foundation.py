"""Explicit canonical résumé foundation for all tailoring workflows."""

from __future__ import annotations

import re
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
DEFAULT_UNSUPPORTED_BRAND_CLAIMS = (
    "FX",
    "Disney Branded Television",
    "National Geographic",
)
DEFAULT_AGE_SIGNALING_EXCLUSIONS = (
    "20+ years",
    "two decades",
    "nearly two decades",
    "seasoned",
    "veteran",
    "decades of experience",
)
DEFAULT_EDUCATION_CLAIM_EXCLUSIONS = (
    "Bachelor's degree",
    "Bachelor degree",
    "Master's degree",
    "Master degree",
    "MBA",
    "doctorate",
    "PhD",
)


class CandidateLanguageError(DataLoadError):
    """Raised when active candidate source or generated copy violates policy."""


def _policy_values(
    configured: dict[str, Any],
    key: str,
    defaults: tuple[str, ...],
) -> tuple[str, ...]:
    constraints = configured.get("claim_constraints") or {}
    return tuple(str(value) for value in constraints.get(key) or defaults)


def candidate_language_violations(
    text: str,
    *,
    unsupported_brands: tuple[str, ...] = DEFAULT_UNSUPPORTED_BRAND_CLAIMS,
    age_signaling: tuple[str, ...] = DEFAULT_AGE_SIGNALING_EXCLUSIONS,
    education_claims: tuple[str, ...] = DEFAULT_EDUCATION_CLAIM_EXCLUSIONS,
) -> list[str]:
    """Return deterministic unsupported-brand and age-signaling matches."""
    violations: list[str] = []
    for phrase in (*unsupported_brands, *age_signaling, *education_claims):
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, str(text or ""), flags=re.IGNORECASE):
            violations.append(phrase)
    return violations


def validate_candidate_language(
    text: str,
    *,
    context: str = "candidate material",
    unsupported_brands: tuple[str, ...] = DEFAULT_UNSUPPORTED_BRAND_CLAIMS,
    age_signaling: tuple[str, ...] = DEFAULT_AGE_SIGNALING_EXCLUSIONS,
    education_claims: tuple[str, ...] = DEFAULT_EDUCATION_CLAIM_EXCLUSIONS,
) -> None:
    """Prevent unsupported brand claims and age-signaling language."""
    violations = candidate_language_violations(
        text,
        unsupported_brands=unsupported_brands,
        age_signaling=age_signaling,
        education_claims=education_claims,
    )
    if violations:
        raise CandidateLanguageError(
            f"{context} violates the Golden Master candidate-language policy: "
            + ", ".join(violations)
        )


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [
            item
            for nested in value.values()
            for item in _flatten_strings(nested)
        ]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten_strings(nested)]
    return [str(value)] if value is not None else []


def _evidence_is_candidate_usable(project: dict[str, Any]) -> bool:
    if str(project.get("status") or "Active") != "Active":
        return False
    if project.get("external_use") is False or project.get("private") is True:
        return False
    usage = str(project.get("usage") or project.get("usage_control") or "").lower()
    return usage not in {
        "private",
        "internal only",
        "do not use externally",
        "exclude",
    }


def _validate_active_foundation(
    loaded: dict[str, Any],
    info: dict[str, Any],
) -> None:
    active_values: list[Any] = []
    for relative_path in info["baseline_files"]:
        key = Path(relative_path).stem
        active_values.append(loaded["data"].get(key, {}))

    evidence_key = Path(info["supplemental_evidence_source"]).stem
    evidence = loaded["data"].get(evidence_key, {}).get("evidence_projects", [])
    active_values.extend(
        project
        for project in evidence
        if isinstance(project, dict) and _evidence_is_candidate_usable(project)
    )
    validate_candidate_language(
        "\n".join(_flatten_strings(active_values)),
        context="Active canonical candidate source",
        unsupported_brands=info["unsupported_brand_claims"],
        age_signaling=info["age_signaling_exclusions"],
        education_claims=info["education_claim_exclusions"],
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
        "approved_content_baseline": str(
            configured.get("approved_content_baseline")
            or "data/canonical_resume/Trisha_Lynch_Golden_Resume_2026.docx"
        ),
        "baseline_files": files,
        "supplemental_evidence_source": str(
            configured.get("supplemental_evidence_source") or "data/evidence_projects.yml"
        ),
        "unsupported_brand_claims": _policy_values(
            configured,
            "unsupported_brand_claims",
            DEFAULT_UNSUPPORTED_BRAND_CLAIMS,
        ),
        "age_signaling_exclusions": _policy_values(
            configured,
            "age_signaling_exclusions",
            DEFAULT_AGE_SIGNALING_EXCLUSIONS,
        ),
        "education_claim_exclusions": _policy_values(
            configured,
            "education_claim_exclusions",
            DEFAULT_EDUCATION_CLAIM_EXCLUSIONS,
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
    info = _foundation_info(root, loaded)
    _validate_active_foundation(loaded, info)
    return loaded
