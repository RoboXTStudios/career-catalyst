"""Small persisted aggregate used by the initial Evidence & Capabilities page."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


EVIDENCE_SUMMARY_PATH = "data/evidence_summary.yml"
SUMMARY_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _review_item(item: dict[str, Any], issue: str, kind: str = "Evidence") -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or item.get("name") or "Untitled item"),
        "kind": kind,
        "issue": issue,
        "confidence": str(item.get("confidence") or ""),
        "verification_status": str(item.get("verification_status") or ""),
    }


def build_evidence_page_summary(
    profile: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    """Build only the lightweight fields required by the summary-first page."""
    evidence = [item for item in profile.get("evidence") or [] if isinstance(item, dict)]
    capabilities = [
        item for item in graph.get("capabilities") or [] if isinstance(item, dict)
    ]
    verified = [
        item for item in evidence
        if item.get("verification_status") in {"Verified", "User Confirmed"}
        and item.get("evidence_type") not in {"Unsupported", "Inferred"}
    ]

    strength_order = {
        "Direct Experience": 0,
        "Strong Adjacent Experience": 1,
        "Transferable Experience": 2,
        "Unsupported": 3,
    }
    confidence_order = {"High": 0, "Medium": 1, "Low": 2}
    top_capabilities = sorted(
        capabilities,
        key=lambda item: (
            0 if item.get("user_review_status") == "Confirmed" else 1,
            strength_order.get(str(item.get("strength")), 9),
            confidence_order.get(str(item.get("confidence")), 9),
            str(item.get("name") or ""),
        ),
    )[:8]

    project_counts: Counter[str] = Counter()
    for item in verified:
        project_counts.update(
            str(value).strip() for value in item.get("related_projects") or []
            if str(value).strip()
        )
    major_projects = [
        {"name": name, "evidence_count": count}
        for name, count in project_counts.most_common(6)
    ]
    not_on_resume = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "Untitled evidence"),
            "company": str(item.get("company") or ""),
            "role": str(item.get("role") or ""),
        }
        for item in verified
        if item.get("resume_visibility") in {"Not Included", "Intentionally Omitted"}
    ][:8]

    category_names = {str(item.get("category") or "") for item in verified}
    strongest_areas: list[str] = []
    area_rules = (
        ("Operations Leadership", {"Operations Leadership", "Campaign Operations", "Transformation", "Governance"}),
        ("Advertising Technology", {"Advertising Technology", "Campaign Operations", "Programmatic", "Platform Implementation"}),
        ("Technical Problem Solving", {"Technical Troubleshooting", "QA", "Measurement", "Launch Readiness"}),
        ("Product and Workflow Design", {"Product Collaboration", "Workflow Design", "Automation"}),
        ("People Development", {"People Leadership", "Training"}),
        ("AI Product and Workflow Leadership", {"AI Systems"}),
    )
    for label, categories in area_rules:
        if category_names & categories:
            strongest_areas.append(label)
    narrative_parts = [
        "senior operations and transformation leader",
        "advertising technology and technical implementation"
        if "Advertising Technology" in strongest_areas else "complex cross-functional operations",
        "product and workflow design"
        if "Product and Workflow Design" in strongest_areas else "workflow improvement",
        "team leadership" if "People Development" in strongest_areas else "stakeholder leadership",
    ]
    if "AI Product and Workflow Leadership" in strongest_areas:
        narrative_parts.append("AI-enabled product development")
    career_profile = (
        f"You are a {narrative_parts[0]} whose experience spans "
        + ", ".join(narrative_parts[1:-1])
        + f", and {narrative_parts[-1]}. Your strongest positioning is at the intersection "
        "of complex operations, product thinking, technical translation, and organizational improvement."
    )
    featured_experience = [
        *(item["name"] for item in major_projects),
        *(
            str(item.get("title"))
            for item in verified
            if item.get("title")
            and str(item.get("title")) not in {project["name"] for project in major_projects}
        ),
    ]
    featured_experience = list(dict.fromkeys(featured_experience))[:8]

    needs_review: list[dict[str, Any]] = []
    for item in profile.get("discoveries") or []:
        if isinstance(item, dict) and item.get("status") == "Awaiting Confirmation":
            needs_review.append(_review_item(item, "Newly inferred evidence needs confirmation."))
    for item in evidence:
        issues: list[str] = []
        if item.get("confidence") == "Low":
            issues.append("Low-confidence evidence needs review.")
        if item.get("verification_status") in {"Needs Review", "Inferred"}:
            issues.append("Evidence is awaiting verification.")
        if item.get("verification_status") == "Unsupported" or item.get("evidence_type") == "Unsupported":
            issues.append("Unsupported claim requires correction or removal.")
        if not str(item.get("description") or "").strip() or not str(item.get("source") or "").strip():
            issues.append("Evidence record is incomplete.")
        for issue in issues:
            needs_review.append(_review_item(item, issue))
    titles: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        title = " ".join(str(item.get("title") or "").lower().split())
        if title:
            titles.setdefault(title, []).append(item)
    for duplicates in titles.values():
        descriptions = {str(item.get("description") or "").strip() for item in duplicates}
        if len(duplicates) > 1 and len(descriptions) > 1:
            needs_review.append(_review_item(duplicates[0], "Conflicting records share this title."))

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": _now(),
        "profile_updated_at": str(profile.get("profile_updated_at") or ""),
        "graph_updated_at": str(graph.get("graph_updated_at") or ""),
        "profile_summary": {
            "career_profile": career_profile,
            "strongest_areas": strongest_areas,
            "featured_projects_and_experience": featured_experience,
            "top_capabilities": [
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or "Unnamed capability"),
                    "strength": str(item.get("strength") or ""),
                }
                for item in top_capabilities
            ],
            "major_projects": major_projects,
            "key_experience_not_on_resume": not_on_resume,
            "total_verified_evidence": len(verified),
            "total_confirmed_capabilities": sum(
                item.get("user_review_status") == "Confirmed" for item in capabilities
            ),
        },
        "needs_review": needs_review,
    }


def save_evidence_page_summary(
    summary: dict[str, Any], project_root: str | Path
) -> Path:
    root = Path(project_root)
    path = root / EVIDENCE_SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(summary, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return path


def load_evidence_page_summary(project_root: str | Path) -> dict[str, Any]:
    """Read the persisted aggregate only; never hydrate the profile or graph."""
    path = Path(project_root) / EVIDENCE_SUMMARY_PATH
    if not path.is_file():
        return {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "summary_missing": True,
            "profile_summary": {
                "career_profile": "",
                "strongest_areas": [],
                "featured_projects_and_experience": [],
                "top_capabilities": [],
                "major_projects": [],
                "key_experience_not_on_resume": [],
                "total_verified_evidence": 0,
                "total_confirmed_capabilities": 0,
            },
            "needs_review": [],
        }
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = dict(loaded) if isinstance(loaded, dict) else {}
    try:
        summary_mtime = path.stat().st_mtime_ns
        result["summary_stale"] = any(
            candidate.is_file() and candidate.stat().st_mtime_ns > summary_mtime
            for candidate in (
                Path(project_root) / "data" / "evidence_profile.yml",
                Path(project_root) / "data" / "capability_graph.yml",
            )
        )
    except OSError:
        result["summary_stale"] = True
    return result


def refresh_evidence_page_summary(
    project_root: str | Path,
    *,
    profile: Optional[dict[str, Any]] = None,
    graph: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Rebuild the aggregate after an explicit evidence/capability mutation."""
    try:
        from .capability_graph import load_capability_graph
        from .evidence_profile import load_evidence_profile
    except ImportError:
        from capability_graph import load_capability_graph
        from evidence_profile import load_evidence_profile

    root = Path(project_root)
    loaded_profile = profile or load_evidence_profile(root)
    loaded_graph = graph or load_capability_graph(root, loaded_profile)
    summary = build_evidence_page_summary(loaded_profile, loaded_graph)
    save_evidence_page_summary(summary, root)
    return summary
