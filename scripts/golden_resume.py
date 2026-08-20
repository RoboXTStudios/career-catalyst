"""Canonical, validated career inventory assembled from existing source YAML.

The Golden Resume is an inventory, not a submission document.  Existing YAML
files remain authoritative; this module supplies the one normalized read path
used by validation, evidence selection, and package readiness checks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .career_claims import PUBLIC_OMG23_NAME
    from .evidence_engine import load_evidence_cards
    from .resume_foundation import load_resume_foundation
except ImportError:
    from career_claims import PUBLIC_OMG23_NAME
    from evidence_engine import load_evidence_cards
    from resume_foundation import load_resume_foundation


CORE_PROJECT_IDS = {"career_catalyst", "roboxt_studios", "campaignos"}
CORE_EVIDENCE_CARD_IDS = {
    "career_catalyst",
    "roboxt_studios",
    "campaignos",
    "github_product_delivery",
}
SENIOR_ENTERPRISE_CARD_IDS = {
    "omg23_disney_leadership",
    "governance_qa_delivery",
    "martech_campaign_execution",
}


class GoldenResumeError(ValueError):
    """Raised when canonical career sources are incomplete or contradictory."""


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _as_records(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get(key, [])
    return [dict(item) for item in value or [] if isinstance(item, Mapping)]


def _record_id(record: Mapping[str, Any], *, prefix: str = "") -> str:
    identifier = str(
        record.get("id")
        or record.get("name")
        or record.get("title")
        or record.get("company")
        or ""
    ).strip()
    slug = _slug(identifier)
    return f"{prefix}{slug}" if prefix else slug


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _flatten(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten(nested)]
    return [str(value)] if value not in (None, "") else []


def _source_references(source: Any) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    for entry in str(source or "").split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        path, identifiers = entry.split(":", 1)
        references.extend(
            (path.strip(), identifier.strip())
            for identifier in identifiers.split(",")
            if identifier.strip()
        )
    return references


def _source_index(data: Mapping[str, Any]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for section, key in (
        ("positions", "positions"),
        ("achievements", "achievements"),
        ("projects", "projects"),
        ("evidence_projects", "evidence_projects"),
    ):
        path = f"data/{section}.yml"
        values = _as_records(data.get(section, {}), key)
        identifiers: set[str] = set()
        for record in values:
            identifiers.update(
                _slug(value)
                for value in (
                    record.get("id"),
                    record.get("name"),
                    record.get("title"),
                    record.get("company"),
                )
                if value
            )
        index[path] = identifiers
    return index


def _normalize_records(
    records: Sequence[Mapping[str, Any]], *, kind: str, prefix: str = "", source_path: str = ""
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["canonical_id"] = _record_id(item, prefix=prefix)
        item["record_type"] = kind
        if source_path:
            item["source_path"] = source_path
        normalized.append(item)
    return normalized


def load_golden_resume(project_root: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the complete canonical career inventory."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    foundation = load_resume_foundation(root)
    data = foundation.get("data", {})
    employment = _normalize_records(
        _as_records(data.get("positions", {}), "positions"),
        kind="employment",
        prefix="employment_",
        source_path="data/positions.yml",
    )
    achievements = _normalize_records(
        _as_records(data.get("achievements", {}), "achievements"),
        kind="achievement",
        prefix="achievement_",
        source_path="data/achievements.yml",
    )
    projects = _normalize_records(
        _as_records(data.get("projects", {}), "projects"),
        kind="project",
        prefix="project_",
        source_path="data/projects.yml",
    )
    evidence_projects = _normalize_records(
        _as_records(data.get("evidence_projects", {}), "evidence_projects"),
        kind="evidence_project",
        prefix="evidence_project_",
        source_path="data/evidence_projects.yml",
    )
    evidence_cards = _normalize_records(
        load_evidence_cards(root), kind="evidence_card", prefix="card_", source_path="config/evidence_cards.yml"
    )
    skill_groups = _normalize_records(
        [
            {"id": name, "name": name.replace("_", " ").title(), "skills": values}
            for name, values in dict((data.get("skills", {}) or {}).get("skill_groups", {})).items()
        ],
        kind="skill_group",
        prefix="skill_group_",
        source_path="data/skills.yml",
    )
    platform_categories = _normalize_records(
        _as_records(data.get("platforms", {}), "platform_categories"),
        kind="platform_category",
        prefix="platform_category_",
        source_path="data/platforms.yml",
    )
    certifications = _normalize_records(
        _as_records(data.get("certifications", {}), "certifications"),
        kind="certification",
        prefix="certification_",
        source_path="data/certifications.yml",
    )
    personal_brand = _normalize_records(
        [
            {
                "id": "candidate_professional_identity",
                "candidate": dict((data.get("personal_brand", {}) or {}).get("candidate", {})),
                "career_profile": dict((data.get("personal_brand", {}) or {}).get("career_profile", {})),
            }
        ],
        kind="personal_brand",
        prefix="personal_brand_",
        source_path="data/personal_brand.yml",
    )
    records = [
        *employment,
        *achievements,
        *projects,
        *evidence_projects,
        *evidence_cards,
        *skill_groups,
        *platform_categories,
        *certifications,
        *personal_brand,
    ]
    inventory = {
        "metadata": {
            "name": "Career Catalyst Golden Resume",
            "kind": "validated_canonical_inventory",
            "source": "existing canonical YAML",
            "submission_document": False,
        },
        "candidate": dict((data.get("personal_brand", {}) or {}).get("candidate", {})),
        "employment": employment,
        "achievements": achievements,
        "projects": projects,
        "evidence_projects": evidence_projects,
        "evidence_cards": evidence_cards,
        "skill_groups": skill_groups,
        "platform_categories": platform_categories,
        "certifications": certifications,
        "personal_brand": personal_brand,
        "records": records,
        "by_id": {str(item["canonical_id"]): item for item in records},
        "claim_corpus": "\n".join(_flatten(records)),
        "foundation": foundation,
    }
    validate_golden_resume(inventory)
    return inventory


def validate_golden_resume(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Fail early when canonical career records drift or lose provenance."""
    errors: list[str] = []
    records = list(inventory.get("records") or [])
    ids = [str(record.get("canonical_id") or "") for record in records]
    if not ids or any(not identifier for identifier in ids):
        errors.append("Every canonical career record requires a stable ID.")
    duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
    if duplicates:
        errors.append("Duplicate canonical career IDs: " + ", ".join(duplicates))

    projects = {str(item.get("id") or "") for item in inventory.get("projects") or []}
    missing_projects = sorted(CORE_PROJECT_IDS - projects)
    if missing_projects:
        errors.append("Missing first-class canonical projects: " + ", ".join(missing_projects))
    cards = {str(item.get("id") or "") for item in inventory.get("evidence_cards") or []}
    missing_cards = sorted(CORE_EVIDENCE_CARD_IDS - cards)
    if missing_cards:
        errors.append("Missing canonical Evidence cards: " + ", ".join(missing_cards))

    employment = list(inventory.get("employment") or [])
    omg23 = next((item for item in employment if "OMG23" in str(item.get("company") or "")), None)
    if not omg23 or str(omg23.get("company") or "") != PUBLIC_OMG23_NAME:
        errors.append(f"Canonical public employer name must be {PUBLIC_OMG23_NAME}.")
    if omg23:
        aliases = {str(value) for value in omg23.get("internal_aliases") or []}
        if not {"OMD Entertainment", "OMG23 / OMD Entertainment"}.issubset(aliases):
            errors.append("Historical OMG23 aliases must remain internal matching aliases.")
        corpus = " ".join(_flatten(omg23))
        if "Led 10 direct reports" not in corpus or "64-person organization" not in corpus:
            errors.append("Canonical OMG23 leadership scope must retain 10 direct reports and 64-person organization.")

    foundation = inventory.get("foundation") or {}
    source_index = _source_index(foundation.get("data", {}))
    for card in inventory.get("evidence_cards") or []:
        source = card.get("source")
        references = _source_references(source)
        if not references:
            if not str(source or "").strip():
                errors.append(f"Evidence card {card.get('id')} has no provenance source.")
            continue
        for path, identifier in references:
            if path not in source_index or _slug(identifier) not in source_index[path]:
                errors.append(
                    f"Evidence card {card.get('id')} has stale provenance {path}:{identifier}."
                )

    career_catalyst = next(
        (item for item in inventory.get("projects") or [] if item.get("id") == "career_catalyst"),
        {},
    )
    repositories = list(career_catalyst.get("repositories") or [])
    if not any(
        str(repo.get("url") or "") == "https://github.com/RoboXTStudios/career-catalyst"
        and str(repo.get("visibility") or "") == "public"
        for repo in repositories
        if isinstance(repo, Mapping)
    ):
        errors.append("Career Catalyst must retain its verified public GitHub repository evidence.")

    if errors:
        raise GoldenResumeError("Golden Resume validation failed: " + " ".join(errors))
    return {
        "status": "valid",
        "record_count": len(records),
        "employment_count": len(employment),
        "project_count": len(inventory.get("projects") or []),
        "evidence_project_count": len(inventory.get("evidence_projects") or []),
        "evidence_card_count": len(inventory.get("evidence_cards") or []),
        "skill_group_count": len(inventory.get("skill_groups") or []),
        "platform_category_count": len(inventory.get("platform_categories") or []),
        "certification_count": len(inventory.get("certifications") or []),
    }


def rank_canonical_evidence_cards(
    cards: Sequence[Mapping[str, Any]], role_text: str
) -> list[dict[str, Any]]:
    """Apply career-credibility priorities without overriding explicit selection."""
    text = str(role_text or "").lower()
    product_ai = bool(re.search(r"\b(ai|artificial intelligence|product|automation|builder|transformation)\b", text))
    media = bool(re.search(r"\b(music|media|content|creative|entertainment|production)\b", text))
    campaign = bool(re.search(r"\b(campaign|martech|adtech|advertising technology|measurement)\b", text))
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for card in cards:
        item = dict(card)
        card_id = str(item.get("id") or "")
        score = 20 if card_id in SENIOR_ENTERPRISE_CARD_IDS else 5
        if product_ai and card_id == "career_catalyst":
            score += 30
        if product_ai and card_id == "github_product_delivery":
            score += 12
        if product_ai and card_id == "campaignos":
            score += 10
        if media and card_id == "roboxt_studios":
            score += 28
        if campaign and card_id == "campaignos":
            score += 18
        item["career_credibility_score"] = score
        ranked.append((score, card_id, item))
    ranked.sort(key=lambda value: (-value[0], value[1]))
    return [item for _score, _card_id, item in ranked]
