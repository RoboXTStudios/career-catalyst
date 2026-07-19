"""Persistent career evidence profile and lightweight knowledge-graph helpers."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


EVIDENCE_PROFILE_PATH = "data/evidence_profile.yml"
SCHEMA_VERSION = 1

EVIDENCE_TYPES = {
    "Direct Experience",
    "User Confirmed",
    "Resume Verified",
    "LinkedIn Verified",
    "Portfolio Verified",
    "Conversation Derived",
    "Imported",
    "Inferred",
    "Unsupported",
}
VERIFICATION_STATUSES = {
    "Verified", "User Confirmed", "Needs Review", "Inferred", "Unsupported"
}
RESUME_VISIBILITIES = {
    "Fully Represented", "Partially Represented", "Not Included", "Intentionally Omitted"
}
CONFIDENCE_LEVELS = {"High", "Medium", "Low"}
EVIDENCE_CATEGORIES = {
    "Advertising Technology", "Marketing Technology", "Campaign Operations",
    "Programmatic", "Measurement", "Analytics", "Platform Implementation",
    "Technical Troubleshooting", "QA", "Launch Readiness", "Data Quality",
    "Workflow Design", "Automation", "Product Collaboration",
    "Cross-functional Leadership", "Operations Leadership", "Transformation",
    "Executive Communication", "Vendor Management", "Client Leadership",
    "Training", "People Leadership", "Governance", "AI Systems",
    "Creative Operations", "Media Operations",
}
USAGE_KEYS = (
    "resume", "resume_recommendations", "cover_letter", "interview", "linkedin", "recruiter_messages",
    "match_scoring", "hiring_manager_lens", "role_interpreter",
    "application_strategy", "career_analytics", "ai_role_gap_analysis",
    "product_role_gap_analysis",
)
CONFIDENCE_SCORE = {"High": 3, "Medium": 2, "Low": 1}
STOP_WORDS = {
    "and", "the", "with", "from", "that", "this", "into", "for", "role",
    "work", "experience", "support", "supporting", "required", "preferred",
    "years", "skills", "strong", "ability", "team", "teams", "across",
}


class EvidenceProfileError(Exception):
    """Raised when an evidence profile cannot be loaded or validated."""


def _root(project_root: str | Path | None = None) -> Path:
    return Path(project_root) if project_root is not None else Path.cwd()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip(" -:;.")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _terms(value: Any) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9+#]+", str(value or "").lower())
        if len(term) >= 3 and term not in STOP_WORDS
    }


def _usage_defaults() -> dict[str, bool]:
    return {key: True for key in USAGE_KEYS}


def normalize_evidence(item: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Return a complete Evidence object with safe additive defaults."""
    current = now or _now()
    result = deepcopy(item)
    title = str(result.get("title") or "Untitled evidence").strip()
    result["id"] = str(result.get("id") or f"evidence_{_slug(title)}")
    result["title"] = title
    result["description"] = str(result.get("description") or "").strip()
    result["category"] = str(result.get("category") or "Operations Leadership")
    result["subcategory"] = str(result.get("subcategory") or "").strip()
    for field in (
        "skills", "platforms", "industries", "clients", "recommended_usage_notes",
        "related_evidence", "related_projects", "related_tools", "positioning_emphases",
        "tags", "notes",
    ):
        value = result.get(field) or []
        result[field] = _dedupe(value if isinstance(value, list) else [value])
    result["evidence_type"] = str(result.get("evidence_type") or "Imported")
    result["source"] = str(result.get("source") or "Manual Entry")
    result["source_reference"] = str(result.get("source_reference") or "").strip()
    result["confidence"] = str(result.get("confidence") or "Medium")
    result["verification_status"] = str(
        result.get("verification_status") or "Needs Review"
    )
    result["resume_visibility"] = str(
        result.get("resume_visibility") or "Not Included"
    )
    usage = _usage_defaults()
    usage.update(
        {
            key: bool(value)
            for key, value in dict(result.get("recommended_usage") or {}).items()
            if key in USAGE_KEYS
        }
    )
    result["recommended_usage"] = usage
    result["career_period"] = str(result.get("career_period") or "").strip()
    result["company"] = str(result.get("company") or "").strip()
    result["role"] = str(result.get("role") or "").strip()
    result["years"] = result.get("years")
    result["technical_depth"] = str(result.get("technical_depth") or "Not specified")
    result["leadership_scope"] = str(result.get("leadership_scope") or "Not specified")
    result["customer_facing"] = str(result.get("customer_facing") or "Not specified")
    result["people_management"] = str(result.get("people_management") or "Not specified")
    provenance = dict(result.get("provenance") or {})
    provenance.setdefault("where", result["source"])
    provenance.setdefault("when", result.get("last_updated") or current)
    provenance.setdefault("how", "Imported into Career Catalyst")
    provenance.setdefault("confidence", result["confidence"])
    result["provenance"] = provenance
    result["created_at"] = str(result.get("created_at") or current)
    result["updated_at"] = str(result.get("updated_at") or current)
    result["last_updated"] = str(result.get("last_updated") or result["updated_at"])
    return result


def validate_evidence(item: dict[str, Any]) -> list[str]:
    """Return validation messages without mutating or discarding user evidence."""
    issues: list[str] = []
    if not str(item.get("id") or "").strip():
        issues.append("Evidence id is required.")
    if not str(item.get("title") or "").strip():
        issues.append("Evidence title is required.")
    if not str(item.get("description") or "").strip():
        issues.append("Evidence description is required.")
    if item.get("evidence_type") not in EVIDENCE_TYPES:
        issues.append("Evidence type is invalid.")
    if item.get("verification_status") not in VERIFICATION_STATUSES:
        issues.append("Verification status is invalid.")
    if item.get("resume_visibility") not in RESUME_VISIBILITIES:
        issues.append("Resume visibility is invalid.")
    if item.get("confidence") not in CONFIDENCE_LEVELS:
        issues.append("Confidence is invalid.")
    if item.get("category") not in EVIDENCE_CATEGORIES:
        issues.append("Evidence category is invalid.")
    return issues


def _legacy_profile(project_root: Path) -> dict[str, Any]:
    """Build an in-memory additive migration from legacy evidence cards."""
    cards_path = project_root / "config" / "evidence_cards.yml"
    cards: list[dict[str, Any]] = []
    if cards_path.is_file():
        loaded = yaml.safe_load(cards_path.read_text(encoding="utf-8")) or {}
        cards = loaded.get("evidence_cards") or []
    now = _now()
    evidence = []
    for card in cards:
        evidence.append(
            normalize_evidence(
                {
                    "id": f"legacy_{card.get('id')}",
                    "title": card.get("label"),
                    "description": card.get("short_description"),
                    "category": "Operations Leadership",
                    "skills": card.get("tags") or [],
                    "evidence_type": "Imported",
                    "source": "Imported Package",
                    "source_reference": card.get("source"),
                    "confidence": str(card.get("confidence_level") or "medium").title(),
                    "verification_status": "Verified",
                    "resume_visibility": "Partially Represented",
                    "related_projects": [card.get("id")],
                    "tags": card.get("tags") or [],
                    "notes": [card.get("when_to_avoid")],
                    "provenance": {
                        "where": "Legacy evidence cards",
                        "when": now,
                        "how": "Automatic additive migration",
                        "confidence": str(card.get("confidence_level") or "medium").title(),
                    },
                },
                now=now,
            )
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_updated_at": now,
        "migration": {
            "status": "derived_in_memory",
            "source": "config/evidence_cards.yml",
            "preserved_resume": True,
        },
        "evidence": evidence,
        "discoveries": [],
    }


def load_evidence_profile(
    project_root: str | Path | None = None,
    *,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Load the canonical profile, deriving legacy evidence safely when absent."""
    root = _root(project_root)
    path = root / EVIDENCE_PROFILE_PATH
    if not path.is_file():
        profile = _legacy_profile(root)
        if create_if_missing:
            save_evidence_profile(profile, root)
        return profile
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise EvidenceProfileError(f"Unable to load evidence profile: {error}") from error
    if not isinstance(loaded, dict):
        raise EvidenceProfileError("Evidence profile must contain a top-level mapping.")
    profile = dict(loaded)
    profile["schema_version"] = int(profile.get("schema_version") or SCHEMA_VERSION)
    profile["evidence"] = [
        normalize_evidence(item)
        for item in profile.get("evidence") or []
        if isinstance(item, dict)
    ]
    profile["discoveries"] = [
        dict(item) for item in profile.get("discoveries") or [] if isinstance(item, dict)
    ]
    return profile


def save_evidence_profile(
    profile: dict[str, Any], project_root: str | Path | None = None
) -> Path:
    """Persist the additive profile without touching resume source files."""
    root = _root(project_root)
    path = root / EVIDENCE_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(profile)
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["profile_updated_at"] = _now()
    normalized["evidence"] = [
        normalize_evidence(item)
        for item in normalized.get("evidence") or []
        if isinstance(item, dict)
    ]
    normalized["discoveries"] = list(normalized.get("discoveries") or [])
    path.write_text(
        yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return path


def usable_evidence(
    profile: dict[str, Any], usage: str | None = None
) -> list[dict[str, Any]]:
    """Return truth-safe evidence eligible for a requested downstream use."""
    result = []
    for item in profile.get("evidence") or []:
        if item.get("verification_status") in {"Unsupported", "Inferred", "Needs Review"}:
            continue
        if item.get("evidence_type") in {"Unsupported", "Inferred"}:
            continue
        if usage and not bool((item.get("recommended_usage") or {}).get(usage)):
            continue
        result.append(item)
    return result


def evidence_text(profile: dict[str, Any], usage: str = "match_scoring") -> str:
    """Flatten verified profile evidence for scoring without treating resume visibility as truth."""
    values: list[str] = []
    for item in usable_evidence(profile, usage):
        for field in (
            "title", "description", "category", "subcategory", "company", "role",
            "technical_depth", "leadership_scope", "customer_facing", "people_management",
        ):
            values.append(str(item.get(field) or ""))
        for field in (
            "skills", "platforms", "industries", "clients", "related_projects",
            "related_tools", "tags",
        ):
            values.extend(str(value) for value in item.get(field) or [])
    return "\n".join(value for value in values if value.strip())


def select_profile_evidence(
    role: dict[str, Any] | str,
    profile: dict[str, Any],
    *,
    usage: str,
    max_items: int = 6,
) -> list[dict[str, Any]]:
    """Rank verified Evidence objects against concrete role language."""
    role_text = (
        str(role)
        if isinstance(role, str)
        else " ".join(
            str(role.get(key) or "")
            for key in (
                "job_title", "title", "raw_text", "job_description", "primary_archetype"
            )
        )
    )
    role_terms = _terms(role_text)
    archetype = str(role.get("primary_archetype") or "") if isinstance(role, dict) else ""
    archetype_category_priorities = {
        "Technical Solutions / Solutions Consulting": {
            "Advertising Technology", "Platform Implementation", "Technical Troubleshooting",
            "Measurement", "QA", "Launch Readiness", "Programmatic",
        },
        "Advertising Technology / Ad Operations": {
            "Advertising Technology", "Platform Implementation", "Technical Troubleshooting",
            "Measurement", "QA", "Launch Readiness", "Programmatic", "Campaign Operations",
        },
        "People Operations": {"People Leadership", "Cross-functional Leadership", "Operations Leadership", "Transformation"},
        "Product Operations": {"Product Collaboration", "Workflow Design", "QA", "Launch Readiness", "AI Systems"},
        "Product Management": {"Product Collaboration", "AI Systems", "Workflow Design", "QA"},
        "Strategic Operations": {"Operations Leadership", "Cross-functional Leadership", "Workflow Design", "Governance", "Transformation"},
    }
    category_priorities = archetype_category_priorities.get(archetype, set())
    title_text = (
        " ".join(str(role.get(key) or "") for key in ("job_title", "title"))
        if isinstance(role, dict) else role_text
    ).lower()
    core_ai_role = any(
        signal in title_text
        for signal in ("ai product", "artificial intelligence", "machine learning product", "ai program", "ai operations")
    )
    advertising_role = archetype in {
        "Technical Solutions / Solutions Consulting", "Advertising Technology / Ad Operations"
    } and any(
        signal in role_text.lower()
        for signal in ("advertiser", "advertising", "ad tech", "adtech", "campaign delivery", "measurement")
    )
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for item in usable_evidence(profile, usage):
        if str(item.get("id") or "").startswith("career_catalyst_") and not core_ai_role:
            continue
        if archetype == "People Operations" and (
            (
                item.get("platforms")
                and item.get("category") not in {
                    "People Leadership", "Cross-functional Leadership", "Campaign Operations",
                    "Operations Leadership", "Workflow Design", "Transformation",
                }
            )
            or item.get("category") in {
                "Advertising Technology", "Platform Implementation", "Programmatic",
                "Measurement", "Technical Troubleshooting",
            }
        ):
            continue
        item_text = " ".join(
            [
                str(item.get("title") or ""), str(item.get("description") or ""),
                str(item.get("category") or ""), str(item.get("subcategory") or ""),
                " ".join(item.get("skills") or []), " ".join(item.get("platforms") or []),
                " ".join(item.get("industries") or []), " ".join(item.get("clients") or []),
                " ".join(item.get("tags") or []),
            ]
        )
        overlap = role_terms & _terms(item_text)
        score = (3 * len(overlap)) + CONFIDENCE_SCORE.get(str(item.get("confidence")), 1)
        if str(item.get("category") or "").lower() in role_text.lower():
            score += 8
        if item.get("category") in category_priorities:
            score += 24
        if item.get("category") == "AI Systems":
            if not core_ai_role:
                continue
            score += 24
        if advertising_role:
            score += 18 if "Advertising" in (item.get("industries") or []) else -18
        platforms = [str(value).lower() for value in item.get("platforms") or []]
        score += 8 * sum(platform in role_text.lower() for platform in platforms if len(platform) >= 4)
        if score >= 8:
            enriched = dict(item)
            enriched["relevance_score"] = score
            enriched["matched_terms"] = sorted(overlap)
            ranked.append((score, str(item.get("id")), enriched))
    ranked.sort(key=lambda value: (-value[0], value[1]))
    return [item for _score, _id, item in ranked[:max_items]]


def evidence_as_card(item: dict[str, Any]) -> dict[str, Any]:
    """Adapt one canonical Evidence object to the legacy evidence-card interface."""
    return {
        "id": str(item.get("id")),
        "label": str(item.get("title")),
        "short_description": str(item.get("description")),
        "proof_points": [str(item.get("description"))],
        "tags": _dedupe(
            [item.get("category"), item.get("subcategory"), *(item.get("skills") or []), *(item.get("tags") or [])]
        ),
        "strongest_role_fits": _dedupe(
            [item.get("category"), item.get("subcategory"), *(item.get("skills") or [])]
        ),
        "when_to_use": "Use only for enabled profile usages and relevant roles.",
        "when_to_avoid": "Do not broaden this user-confirmed evidence beyond its stated ownership boundary.",
        "confidence_level": str(item.get("confidence") or "Medium").lower(),
        "source": f"{item.get('source')}: {item.get('source_reference')}",
        "evidence_profile": True,
        "resume_visibility": item.get("resume_visibility"),
        "verification_status": item.get("verification_status"),
        "recommended_usage": dict(item.get("recommended_usage") or {}),
    }


def discover_evidence(
    title: str,
    description: str,
    *,
    source: str = "Conversation",
    source_reference: str = "",
    category: str = "Operations Leadership",
) -> dict[str, Any]:
    """Create a review proposal; inferred evidence is never added directly."""
    now = _now()
    return {
        "id": f"discovery_{_slug(title)}_{now[:10].replace('-', '')}",
        "title": str(title).strip(),
        "description": str(description).strip(),
        "category": category,
        "source": source,
        "source_reference": source_reference,
        "confidence": "Medium",
        "verification_status": "Needs Review",
        "evidence_type": "Conversation Derived",
        "status": "Awaiting Confirmation",
        "discovered_at": now,
    }


def add_discovery(
    profile: dict[str, Any], discovery: dict[str, Any]
) -> dict[str, Any]:
    result = deepcopy(profile)
    result.setdefault("discoveries", []).append(dict(discovery))
    return result


def confirm_discovery(
    profile: dict[str, Any], discovery_id: str, edits: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Promote a reviewed discovery to user-confirmed evidence."""
    result = deepcopy(profile)
    discovery = next(
        (
            item for item in result.get("discoveries") or []
            if str(item.get("id")) == str(discovery_id)
        ),
        None,
    )
    if discovery is None:
        raise EvidenceProfileError(f"Evidence discovery '{discovery_id}' was not found.")
    values = {**discovery, **dict(edits or {})}
    values.update(
        {
            "id": str(values.get("evidence_id") or values.get("id")).replace("discovery_", "evidence_", 1),
            "evidence_type": "User Confirmed",
            "verification_status": "User Confirmed",
            "confidence": "High",
            "resume_visibility": values.get("resume_visibility") or "Not Included",
            "provenance": {
                "where": values.get("source") or "Conversation",
                "when": values.get("discovered_at") or _now(),
                "how": "User confirmed an evidence discovery",
                "confidence": "High",
            },
        }
    )
    evidence = normalize_evidence(values)
    issues = validate_evidence(evidence)
    if issues:
        raise EvidenceProfileError(" ".join(issues))
    result.setdefault("evidence", []).append(evidence)
    discovery["status"] = "Confirmed"
    discovery["confirmed_evidence_id"] = evidence["id"]
    return result


def reject_discovery(profile: dict[str, Any], discovery_id: str) -> dict[str, Any]:
    result = deepcopy(profile)
    discovery = next(
        (
            item for item in result.get("discoveries") or []
            if str(item.get("id")) == str(discovery_id)
        ),
        None,
    )
    if discovery is None:
        raise EvidenceProfileError(f"Evidence discovery '{discovery_id}' was not found.")
    discovery["status"] = "Rejected"
    discovery["rejected_at"] = _now()
    return result


def related_evidence(profile: dict[str, Any], evidence_id: str) -> list[dict[str, Any]]:
    """Return explicit and reciprocal evidence relationships."""
    items = {str(item.get("id")): item for item in profile.get("evidence") or []}
    target = items.get(str(evidence_id))
    if not target:
        return []
    related_ids = set(str(value) for value in target.get("related_evidence") or [])
    related_ids.update(
        item_id
        for item_id, item in items.items()
        if str(evidence_id) in {str(value) for value in item.get("related_evidence") or []}
    )
    return [items[item_id] for item_id in sorted(related_ids) if item_id in items]


def query_evidence(
    profile: dict[str, Any],
    *,
    search: str = "",
    category: str = "",
    confidence: str = "",
    source: str = "",
    resume_visibility: str = "",
    usage: str = "",
    verification: str = "",
) -> list[dict[str, Any]]:
    """Filter the Evidence Explorer without modifying the stored profile."""
    needle = search.lower().strip()
    result = []
    for item in profile.get("evidence") or []:
        searchable = " ".join(
            str(value)
            for value in (
                item.get("title"), item.get("description"), item.get("category"),
                item.get("subcategory"), item.get("skills"), item.get("platforms"),
                item.get("industries"), item.get("clients"), item.get("company"),
                item.get("role"), item.get("tags"),
            )
        ).lower()
        if needle and needle not in searchable:
            continue
        if category and item.get("category") != category:
            continue
        if confidence and item.get("confidence") != confidence:
            continue
        if source and item.get("source") != source:
            continue
        if resume_visibility and item.get("resume_visibility") != resume_visibility:
            continue
        if verification and item.get("verification_status") != verification:
            continue
        if usage and not bool((item.get("recommended_usage") or {}).get(usage)):
            continue
        result.append(item)
    return result


def evidence_gap_analysis(
    requirements: Iterable[Any], profile: dict[str, Any], resume_text: str = ""
) -> dict[str, list[dict[str, Any]]]:
    """Keep resume-language, confirmation, unsupported, and true gaps separate."""
    result: dict[str, list[dict[str, Any]]] = {
        "missing_because_not_on_resume": [],
        "missing_because_unsupported": [],
        "missing_because_needs_confirmation": [],
        "missing_because_truly_absent": [],
    }
    items = list(profile.get("evidence") or [])
    resume_lower = resume_text.lower()
    for raw_requirement in requirements:
        requirement = str(
            raw_requirement.get("requirement")
            if isinstance(raw_requirement, dict)
            else raw_requirement
        ).strip()
        if not requirement:
            continue
        requirement_terms = _terms(requirement)
        matches = []
        for item in items:
            item_terms = _terms(
                " ".join(
                    [
                        str(item.get("title") or ""), str(item.get("description") or ""),
                        str(item.get("category") or ""), " ".join(item.get("skills") or []),
                        " ".join(item.get("platforms") or []), " ".join(item.get("tags") or []),
                    ]
                )
            )
            overlap = requirement_terms & item_terms
            if overlap and len(overlap) >= min(2, len(requirement_terms)):
                matches.append(item)
        verified = [
            item for item in matches
            if item.get("verification_status") in {"Verified", "User Confirmed"}
            and item.get("evidence_type") != "Unsupported"
        ]
        pending = [
            item for item in matches
            if item.get("verification_status") in {"Needs Review", "Inferred"}
        ]
        unsupported = [
            item for item in matches
            if item.get("verification_status") == "Unsupported"
            or item.get("evidence_type") == "Unsupported"
        ]
        resume_has_language = bool(requirement_terms and requirement_terms <= _terms(resume_lower))
        if verified and not resume_has_language and any(
            item.get("resume_visibility") in {"Not Included", "Intentionally Omitted", "Partially Represented"}
            for item in verified
        ):
            result["missing_because_not_on_resume"].append(
                {"requirement": requirement, "evidence_ids": [item["id"] for item in verified]}
            )
        elif pending:
            result["missing_because_needs_confirmation"].append(
                {"requirement": requirement, "evidence_ids": [item["id"] for item in pending]}
            )
        elif unsupported:
            result["missing_because_unsupported"].append(
                {"requirement": requirement, "evidence_ids": [item["id"] for item in unsupported]}
            )
        elif not verified and not resume_has_language:
            result["missing_because_truly_absent"].append(
                {"requirement": requirement, "evidence_ids": []}
            )
    return result


def evidence_explorer_summary(profile: dict[str, Any]) -> dict[str, Any]:
    evidence = list(profile.get("evidence") or [])
    categories: dict[str, int] = {}
    for item in evidence:
        category = str(item.get("category") or "Uncategorized")
        categories[category] = categories.get(category, 0) + 1
    recent = sorted(
        evidence, key=lambda item: str(item.get("updated_at") or ""), reverse=True
    )[:5]
    awaiting = [
        item for item in profile.get("discoveries") or []
        if item.get("status") == "Awaiting Confirmation"
    ]
    return {
        "total_evidence": len(evidence),
        "categories": dict(sorted(categories.items())),
        "recent_evidence": recent,
        "awaiting_confirmation": awaiting,
        "verified_count": sum(
            item.get("verification_status") in {"Verified", "User Confirmed"}
            for item in evidence
        ),
        "not_on_resume_count": sum(
            item.get("resume_visibility") in {"Not Included", "Intentionally Omitted"}
            for item in evidence
        ),
    }
