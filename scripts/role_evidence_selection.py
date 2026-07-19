"""Automatic, concise, and reviewable evidence selection for one prospect."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

try:
    from .evidence_profile import select_profile_evidence, usable_evidence
except ImportError:
    from evidence_profile import select_profile_evidence, usable_evidence


SELECTION_VERSION = 2
SELECTION_BUCKETS = ("primary_evidence", "supporting_evidence")
OVERRIDE_FIELDS = ("included_ids", "excluded_ids", "primary_ids", "supporting_ids")
AUTOMATIC_PRIMARY_LIMIT = 5
AUTOMATIC_SUPPORTING_LIMIT = 3
AUTOMATIC_TOTAL_LIMIT = 8


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
    """Normalize both Sprint 24.2 overrides and the legacy override representation."""
    source = dict(overrides or {})
    priorities = {
        str(key): str(value).title()
        for key, value in dict(source.get("manual_priority_overrides") or {}).items()
        if str(value).title() in {"Primary", "Supporting"}
    }
    additions = _dedupe(
        [*(source.get("manual_additions") or []), *(source.get("included_ids") or [])]
    )
    exclusions = _dedupe(
        [*(source.get("manual_exclusions") or []), *(source.get("excluded_ids") or [])]
    )
    primary = _dedupe(
        [
            *(source.get("primary_ids") or []),
            *(key for key, value in priorities.items() if value == "Primary"),
        ]
    )
    supporting = _dedupe(
        [
            *(source.get("supporting_ids") or []),
            *(key for key, value in priorities.items() if value == "Supporting"),
        ]
    )
    if valid_ids is not None:
        additions = [value for value in additions if value in valid_ids]
        exclusions = [value for value in exclusions if value in valid_ids]
        primary = [value for value in primary if value in valid_ids]
        supporting = [value for value in supporting if value in valid_ids]
    excluded = set(exclusions)
    additions = [value for value in additions if value not in excluded]
    primary = [value for value in primary if value not in excluded]
    primary_set = set(primary)
    supporting = [
        value for value in supporting if value not in excluded and value not in primary_set
    ]
    priorities = {
        **{value: "Primary" for value in primary},
        **{value: "Supporting" for value in supporting},
    }
    reviewed = bool(
        source.get("user_reviewed") or additions or exclusions or priorities
    )
    return {
        "manual_additions": additions,
        "manual_exclusions": exclusions,
        "manual_priority_overrides": priorities,
        # Additive compatibility for persisted Sprint 24.1 prospects.
        "included_ids": additions,
        "excluded_ids": exclusions,
        "primary_ids": primary,
        "supporting_ids": supporting,
        "user_reviewed": reviewed,
    }


def migrate_legacy_selection_to_overrides(
    selection: Optional[dict[str, Any]], overrides: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Convert only demonstrably manual legacy choices; never reinterpret automatic picks."""
    if overrides:
        return normalize_selection_overrides(overrides)
    source = dict(selection or {})
    embedded = source.get("overrides")
    if isinstance(embedded, dict) and embedded:
        return normalize_selection_overrides(embedded)
    additions: list[str] = []
    primary: list[str] = []
    supporting: list[str] = []
    for bucket, target in (
        ("primary_evidence", primary),
        ("supporting_evidence", supporting),
        ("transferable_evidence", supporting),
    ):
        for item in source.get(bucket) or []:
            if not isinstance(item, dict) or item.get("selected_by") != "User override":
                continue
            evidence_id = str(item.get("id") or "").strip()
            if evidence_id:
                additions.append(evidence_id)
                target.append(evidence_id)
    exclusions = [
        str(item.get("id"))
        for item in source.get("excluded_evidence") or []
        if isinstance(item, dict) and item.get("excluded_by") == "User override"
    ]
    return normalize_selection_overrides(
        {
            "manual_additions": additions,
            "manual_exclusions": exclusions,
            "primary_ids": primary,
            "supporting_ids": supporting,
        }
    )


def update_selection_overrides(
    overrides: Optional[dict[str, Any]],
    evidence_id: str,
    action: str,
    *,
    replacement_id: str = "",
) -> dict[str, Any]:
    """Apply one prospect-only action without modifying the global Evidence Profile."""
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


def _item_terms(item: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            str(item.get("category") or ""),
            " ".join(str(value) for value in item.get("skills") or []),
            " ".join(str(value) for value in item.get("tags") or []),
        ]
    ).lower()
    return {
        value for value in re.findall(r"[a-z0-9]+", text)
        if len(value) >= 4 and value not in {"with", "from", "that", "this", "across"}
    }


def _is_redundant(item: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    terms = _item_terms(item)
    projects = set(str(value) for value in item.get("related_projects") or [])
    for existing in selected:
        existing_terms = _item_terms(existing)
        union = terms | existing_terms
        similarity = len(terms & existing_terms) / len(union) if union else 0.0
        shared_projects = projects & set(
            str(value) for value in existing.get("related_projects") or []
        )
        if similarity >= 0.72 or (shared_projects and similarity >= 0.48):
            return True
    return False


def _recency_score(item: dict[str, Any]) -> float:
    raw = str(item.get("last_updated") or item.get("updated_at") or "")
    try:
        year = datetime.fromisoformat(raw.replace("Z", "+00:00")).year
    except ValueError:
        matches = re.findall(r"(?:19|20)\d{2}", str(item.get("career_period") or raw))
        year = max((int(value) for value in matches), default=0)
    if not year:
        return 0.5
    age = max(0, datetime.now(timezone.utc).year - year)
    return max(0.0, 3.0 - min(age, 12) * 0.25)


def _scope_score(item: dict[str, Any]) -> float:
    text = " ".join(
        str(item.get(field) or "")
        for field in ("leadership_scope", "people_management", "customer_facing", "description")
    ).lower()
    signals = ("enterprise", "global", "executive", "cross-functional", "portfolio", "team", "led", "owned")
    return min(4.0, 0.8 * sum(signal in text for signal in signals))


def _selection_fingerprint(
    role: dict[str, Any], evidence: Iterable[dict[str, Any]], usage: str
) -> str:
    payload = {
        "role": {
            key: role.get(key)
            for key in ("job_title", "title", "raw_text", "job_description", "primary_archetype")
        },
        "evidence": [
            (str(item.get("id")), str(item.get("updated_at") or item.get("last_updated") or ""))
            for item in evidence
        ],
        "usage": usage,
        "version": SELECTION_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


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
    else:
        reasons.append("Adds relevant proof or context without duplicating the primary evidence.")
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
    max_automatic: int = AUTOMATIC_TOTAL_LIMIT,
) -> dict[str, Any]:
    """Rank a concise automatic set, then layer independent manual overrides onto it."""
    matrix = list(alignment_matrix or [])
    all_usable = usable_evidence(evidence_profile, usage)
    evidence_by_id = {str(item.get("id")): item for item in all_usable}
    valid_ids = set(evidence_by_id)
    normalized_overrides = normalize_selection_overrides(overrides, valid_ids)

    direct_counts: dict[str, int] = {}
    adjacent_counts: dict[str, int] = {}
    importance: dict[str, float] = {}
    for index, row in enumerate(matrix):
        level = str(row.get("alignment_level") or "")
        target = direct_counts if level == "Direct" else adjacent_counts
        role_weight = max(1.0, 5.0 - (index * 0.35))
        if row.get("requirement_type") == "Hard Gate":
            role_weight += 3.0
        elif row.get("requirement_type") == "Strong Preference":
            role_weight += 1.5
        for evidence_id in row.get("supporting_evidence_ids") or []:
            key = str(evidence_id)
            target[key] = target.get(key, 0) + 1
            importance[key] = importance.get(key, 0.0) + role_weight

    ranked = select_profile_evidence(
        role, evidence_profile, usage=usage, max_items=max(24, max_automatic * 3)
    )
    confidence = {"High": 3.0, "Medium": 1.8, "Low": 0.5}
    for item in ranked:
        evidence_id = str(item.get("id"))
        item["selection_score"] = round(
            float(item.get("relevance_score") or 0)
            + confidence.get(str(item.get("confidence")), 0.5)
            + _recency_score(item)
            + _scope_score(item)
            + (6.0 * direct_counts.get(evidence_id, 0))
            + (2.5 * adjacent_counts.get(evidence_id, 0))
            + importance.get(evidence_id, 0.0),
            2,
        )
    ranked.sort(key=lambda item: (-float(item.get("selection_score") or 0), str(item.get("id"))))

    automatic: list[dict[str, Any]] = []
    limit = min(AUTOMATIC_TOTAL_LIMIT, max(1, int(max_automatic)))
    for item in ranked:
        if len(automatic) >= limit:
            break
        if _is_redundant(item, automatic):
            continue
        automatic.append(item)

    direct_candidates = [
        item for item in automatic if str(item.get("id")) in direct_counts
    ]
    adjacent_candidates = [
        item for item in automatic if str(item.get("id")) not in direct_counts
    ]
    desired_primary = min(AUTOMATIC_PRIMARY_LIMIT, max(3, len(direct_candidates)))
    automatic_primary = direct_candidates[:desired_primary]
    if len(automatic_primary) < min(3, len(automatic)):
        for item in adjacent_candidates:
            if item not in automatic_primary:
                automatic_primary.append(item)
            if len(automatic_primary) >= min(3, len(automatic)):
                break
    primary_ids = [str(item.get("id")) for item in automatic_primary[:AUTOMATIC_PRIMARY_LIMIT]]
    supporting_ids = [
        str(item.get("id")) for item in automatic if str(item.get("id")) not in set(primary_ids)
    ][:AUTOMATIC_SUPPORTING_LIMIT]

    excluded = set(normalized_overrides["manual_exclusions"])
    primary_ids = [value for value in primary_ids if value not in excluded]
    supporting_ids = [value for value in supporting_ids if value not in excluded]
    for evidence_id in normalized_overrides["manual_additions"]:
        if evidence_id not in primary_ids and evidence_id not in supporting_ids:
            supporting_ids.append(evidence_id)
    for evidence_id, level in normalized_overrides["manual_priority_overrides"].items():
        primary_ids = [value for value in primary_ids if value != evidence_id]
        supporting_ids = [value for value in supporting_ids if value != evidence_id]
        if evidence_id in evidence_by_id and evidence_id not in excluded:
            (primary_ids if level == "Primary" else supporting_ids).insert(0, evidence_id)

    priority_ids = set(normalized_overrides["manual_priority_overrides"])
    addition_ids = set(normalized_overrides["manual_additions"])
    primary = [
        _selection_item(
            evidence_by_id[value], "Primary", direct_counts.get(value, 0),
            value in priority_ids or value in addition_ids,
        )
        for value in _dedupe(primary_ids) if value in evidence_by_id
    ]
    supporting = [
        _selection_item(
            evidence_by_id[value], "Supporting",
            direct_counts.get(value, 0) or adjacent_counts.get(value, 0),
            value in priority_ids or value in addition_ids,
        )
        for value in _dedupe(supporting_ids) if value in evidence_by_id
    ]
    selected_ids = _dedupe(
        [*(item["id"] for item in primary), *(item["id"] for item in supporting)]
    )

    excluded_summaries = []
    for item in all_usable:
        evidence_id = str(item.get("id"))
        if evidence_id in selected_ids:
            continue
        explicit = evidence_id in excluded
        excluded_summaries.append(
            {
                "id": evidence_id,
                "title": item.get("title"),
                "category": item.get("category"),
                "excluded_by": "User override" if explicit else "Automatic relevance filter",
                "exclusion_reason": (
                    "Excluded by the user for this prospect."
                    if explicit
                    else "A stronger or more role-specific item was selected."
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
        known_gaps.append(
            {
                "requirement": item.get("requirement"),
                "reason": "Potential evidence exists but still needs user confirmation.",
                "requirement_type": "Needs Confirmation",
            }
        )

    important_capabilities: list[str] = []
    for row in matrix:
        for capability in row.get("derived_capabilities") or []:
            if capability not in important_capabilities:
                important_capabilities.append(capability)
    automatic_primary_ids = [
        value for value in [str(item.get("id")) for item in automatic_primary]
        if value not in excluded
    ][:AUTOMATIC_PRIMARY_LIMIT]
    automatic_supporting_ids = [
        str(item.get("id")) for item in automatic
        if str(item.get("id")) not in set(automatic_primary_ids) and str(item.get("id")) not in excluded
    ][:AUTOMATIC_SUPPORTING_LIMIT]
    legacy_transferable = [
        item for item in supporting if str(item.get("id")) in adjacent_counts
    ]
    return {
        "selection_version": SELECTION_VERSION,
        "automatic_by_default": True,
        "selection_fingerprint": _selection_fingerprint(role, all_usable, usage),
        "important_capabilities": important_capabilities,
        "automatic_selection": {
            "primary_ids": automatic_primary_ids,
            "supporting_ids": automatic_supporting_ids,
            "selected_evidence_ids": _dedupe([*automatic_primary_ids, *automatic_supporting_ids]),
        },
        "manual_additions": list(normalized_overrides["manual_additions"]),
        "manual_exclusions": list(normalized_overrides["manual_exclusions"]),
        "manual_priority_overrides": dict(normalized_overrides["manual_priority_overrides"]),
        "primary_evidence": primary,
        "supporting_evidence": supporting,
        # Read-only compatibility alias. These items remain classified as Supporting.
        "transferable_evidence": legacy_transferable,
        "known_gaps": known_gaps,
        "excluded_evidence": excluded_summaries,
        "selected_evidence_ids": selected_ids,
        "overrides": normalized_overrides,
        "selection_summary": {
            "primary": len(primary),
            "supporting": len(supporting),
            "transferable": 0,
            "known_gaps": len(known_gaps),
            "excluded": len(excluded_summaries),
        },
    }


def selected_evidence(selection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the exact final evidence set in package-generation priority order."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in SELECTION_BUCKETS:
        for item in selection.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("id") or "")
            if evidence_id and evidence_id not in seen:
                seen.add(evidence_id)
                result.append(item)
    return result
