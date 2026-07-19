"""Automatic, reviewable evidence selection for one interpreted prospect."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Optional

try:
    from .evidence_profile import select_profile_evidence, usable_evidence
except ImportError:
    from evidence_profile import select_profile_evidence, usable_evidence


SELECTION_VERSION = 1
SELECTION_BUCKETS = (
    "primary_evidence", "supporting_evidence", "transferable_evidence"
)
OVERRIDE_FIELDS = (
    "included_ids", "excluded_ids", "primary_ids", "supporting_ids"
)


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def normalize_selection_overrides(
    overrides: Optional[dict[str, Any]], valid_ids: Optional[set[str]] = None
) -> dict[str, Any]:
    """Keep prospect overrides small, additive, and independent of global evidence."""
    source = dict(overrides or {})
    result: dict[str, Any] = {
        field: _dedupe(source.get(field) or []) for field in OVERRIDE_FIELDS
    }
    if valid_ids is not None:
        for field in OVERRIDE_FIELDS:
            result[field] = [value for value in result[field] if value in valid_ids]
    excluded = set(result["excluded_ids"])
    result["included_ids"] = [
        value for value in result["included_ids"] if value not in excluded
    ]
    result["primary_ids"] = [
        value for value in result["primary_ids"] if value not in excluded
    ]
    result["supporting_ids"] = [
        value for value in result["supporting_ids"]
        if value not in excluded and value not in set(result["primary_ids"])
    ]
    result["user_reviewed"] = bool(
        source.get("user_reviewed")
        or any(result[field] for field in OVERRIDE_FIELDS)
    )
    return result


def update_selection_overrides(
    overrides: Optional[dict[str, Any]],
    evidence_id: str,
    action: str,
    *,
    replacement_id: str = "",
) -> dict[str, Any]:
    """Apply one lightweight prospect-level action without modifying Evidence Profile."""
    if action == "reset":
        return normalize_selection_overrides({})
    result = normalize_selection_overrides(overrides)
    evidence_id = str(evidence_id or "").strip()
    replacement_id = str(replacement_id or "").strip()
    for field in OVERRIDE_FIELDS:
        result[field] = [value for value in result[field] if value != evidence_id]
    if action == "include":
        result["included_ids"].append(evidence_id)
    elif action == "exclude":
        result["excluded_ids"].append(evidence_id)
    elif action == "make_primary":
        result["included_ids"].append(evidence_id)
        result["primary_ids"].append(evidence_id)
    elif action == "demote_supporting":
        result["included_ids"].append(evidence_id)
        result["supporting_ids"].append(evidence_id)
    elif action == "replace":
        result["excluded_ids"].append(evidence_id)
        if replacement_id:
            result["included_ids"].append(replacement_id)
    else:
        raise ValueError(f"Unknown evidence-selection action: {action}")
    result["user_reviewed"] = True
    return normalize_selection_overrides(result)


def _why_selected(
    item: dict[str, Any], level: str, requirement_count: int, user_selected: bool
) -> list[str]:
    reasons = []
    if user_selected:
        reasons.append("Included by the user for this prospect.")
    if level == "Primary":
        reasons.append(
            f"Supports {requirement_count or 1} directly aligned role requirement(s)."
        )
    elif level == "Supporting":
        reasons.append("Adds relevant proof, depth, or context to the primary evidence.")
    else:
        reasons.append(
            "Demonstrates a comparable capability in an adjacent function or context."
        )
    if item.get("confidence"):
        reasons.append(f"{item.get('confidence')}-confidence {item.get('verification_status')} evidence.")
    if item.get("matched_terms"):
        reasons.append("Matched role signals: " + ", ".join(item["matched_terms"][:6]) + ".")
    return reasons


def _selection_item(
    item: dict[str, Any], level: str, requirement_count: int, user_selected: bool
) -> dict[str, Any]:
    return {
        **deepcopy(item),
        "selection_level": level,
        "why_selected": _why_selected(item, level, requirement_count, user_selected),
        "requirement_support_count": requirement_count,
        "selected_by": "User override" if user_selected else "Automatic selection",
    }


def build_role_evidence_selection(
    role: dict[str, Any],
    evidence_profile: dict[str, Any],
    alignment_matrix: Optional[list[dict[str, Any]]] = None,
    gap_analysis: Optional[dict[str, Any]] = None,
    overrides: Optional[dict[str, Any]] = None,
    *,
    usage: str = "application_strategy",
    max_automatic: int = 11,
) -> dict[str, Any]:
    """Select evidence automatically, then apply prospect-only user overrides."""
    matrix = list(alignment_matrix or [])
    evidence_by_id = {
        str(item.get("id")): item for item in usable_evidence(evidence_profile, usage)
    }
    valid_ids = set(evidence_by_id)
    normalized_overrides = normalize_selection_overrides(overrides, valid_ids)
    ranked = select_profile_evidence(
        role, evidence_profile, usage=usage, max_items=max_automatic
    )
    ranked_ids = [str(item.get("id")) for item in ranked]
    included_ids = _dedupe(
        [*ranked_ids, *normalized_overrides["included_ids"], *normalized_overrides["primary_ids"], *normalized_overrides["supporting_ids"]]
    )
    excluded_ids = set(normalized_overrides["excluded_ids"])
    included_ids = [value for value in included_ids if value not in excluded_ids]

    direct_counts: dict[str, int] = {}
    adjacent_counts: dict[str, int] = {}
    for row in matrix:
        target = (
            direct_counts
            if row.get("alignment_level") == "Direct"
            else adjacent_counts
            if row.get("alignment_level") in {"Strong Adjacent", "Transferable"}
            else None
        )
        if target is None:
            continue
        for evidence_id in row.get("supporting_evidence_ids") or []:
            target[str(evidence_id)] = target.get(str(evidence_id), 0) + 1

    forced_primary = set(normalized_overrides["primary_ids"])
    forced_supporting = set(normalized_overrides["supporting_ids"])
    explicitly_included = set(normalized_overrides["included_ids"]) - forced_primary

    def user_first(
        user_ids: Iterable[str], automatic_ids: Iterable[str], automatic_limit: int
    ) -> list[str]:
        priority = _dedupe(user_ids)
        priority_set = set(priority)
        automatic = [
            value for value in _dedupe(automatic_ids) if value not in priority_set
        ]
        return [*priority, *automatic[:max(0, automatic_limit - len(priority))]]

    primary_ids = user_first(
        (value for value in included_ids if value in forced_primary),
        (
            value for value in included_ids
            if value in direct_counts
            and value not in forced_supporting
            and value not in explicitly_included
        ),
        3,
    )
    if not primary_ids:
        primary_ids = included_ids[: min(2, len(included_ids))]
    primary_set = set(primary_ids)
    transferable_ids = user_first(
        (),
        (
            value for value in included_ids
            if value not in primary_set
            and value not in forced_supporting
            and value not in explicitly_included
            and value in adjacent_counts
        ),
        4,
    )
    transferable_set = set(transferable_ids)
    supporting_ids = user_first(
        (
            value for value in included_ids
            if value in forced_supporting or value in explicitly_included
        ),
        (
            value for value in included_ids
            if value not in primary_set and value not in transferable_set
        ),
        5,
    )

    primary = [
        _selection_item(evidence_by_id[value], "Primary", direct_counts.get(value, 0), value in forced_primary)
        for value in primary_ids if value in evidence_by_id
    ]
    supporting = [
        _selection_item(evidence_by_id[value], "Supporting", direct_counts.get(value, 0), value in forced_supporting or value in normalized_overrides["included_ids"])
        for value in supporting_ids if value in evidence_by_id
    ]
    transferable = [
        _selection_item(evidence_by_id[value], "Transferable", adjacent_counts.get(value, 0), value in normalized_overrides["included_ids"])
        for value in transferable_ids if value in evidence_by_id
    ]
    selected_ids = _dedupe([
        *(item["id"] for item in primary),
        *(item["id"] for item in supporting),
        *(item["id"] for item in transferable),
    ])

    excluded = []
    for item in usable_evidence(evidence_profile, usage):
        evidence_id = str(item.get("id"))
        if evidence_id in selected_ids:
            continue
        explicit = evidence_id in excluded_ids
        excluded.append(
            {
                **deepcopy(item),
                "excluded_by": "User override" if explicit else "Automatic relevance filter",
                "exclusion_reason": (
                    "Excluded by the user for this prospect."
                    if explicit
                    else "Not selected because stronger, more role-specific evidence is available."
                ),
            }
        )

    known_gaps = [
        {
            "requirement": row.get("requirement"),
            "reason": row.get("remaining_gap") or "No verified supporting evidence was found.",
            "requirement_type": row.get("requirement_type"),
        }
        for row in matrix if row.get("alignment_level") == "Unsupported"
    ]
    for item in (gap_analysis or {}).get("missing_because_needs_confirmation") or []:
        known_gaps.append({
            "requirement": item.get("requirement"),
            "reason": "Potential evidence exists but still needs user confirmation.",
            "requirement_type": "Needs Confirmation",
        })

    important_capabilities = []
    for row in matrix:
        for capability in row.get("derived_capabilities") or []:
            if capability not in important_capabilities:
                important_capabilities.append(capability)
    return {
        "selection_version": SELECTION_VERSION,
        "automatic_by_default": True,
        "important_capabilities": important_capabilities,
        "primary_evidence": primary,
        "supporting_evidence": supporting,
        "transferable_evidence": transferable,
        "known_gaps": known_gaps,
        "excluded_evidence": excluded,
        "selected_evidence_ids": selected_ids,
        "overrides": normalized_overrides,
        "selection_summary": {
            "primary": len(primary),
            "supporting": len(supporting),
            "transferable": len(transferable),
            "known_gaps": len(known_gaps),
            "excluded": len(excluded),
        },
    }


def selected_evidence(selection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the exact prospect evidence set in package-generation priority order."""
    return [
        item
        for bucket in SELECTION_BUCKETS
        for item in selection.get(bucket) or []
        if isinstance(item, dict)
    ]
