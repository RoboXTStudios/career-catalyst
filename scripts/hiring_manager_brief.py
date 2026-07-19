"""Human-readable prospect briefing derived from persisted structured analysis."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable


BRIEF_VERSION = 1
DEFAULT_INTERNAL_TERMS = (
    "evidence profile",
    "capability graph",
    "primary evidence",
    "supporting evidence",
    "direct / adjacent / transferable",
    "derivation type",
    "confidence calculation",
    "selection score",
    "adjacent",
    "transferable",
    "provenance",
    "derivation type",
)

THEME_HEADINGS = {
    "Advertising Technology": "Advertising Platform Expertise",
    "Platform Implementation": "Advertising Platform Expertise",
    "Programmatic": "Advertising Platform Expertise",
    "Technical Troubleshooting": "Technical Problem Solving",
    "QA": "Measurement and Delivery Reliability",
    "Measurement": "Measurement and Delivery Reliability",
    "Launch Readiness": "Measurement and Delivery Reliability",
    "Campaign Operations": "Operations Leadership",
    "Operations Leadership": "Operations Leadership",
    "Cross-functional Leadership": "Leadership and Technical Translation",
    "People Leadership": "People and Team Leadership",
    "Workflow Design": "Product and Workflow Design",
    "Product Collaboration": "Product and Workflow Design",
    "Transformation": "Transformation and Organizational Improvement",
    "Governance": "Transformation and Organizational Improvement",
    "AI Systems": "AI Product and Workflow Leadership",
}


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


def _sentence(value: Any, maximum: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s+", text)[0]
    if len(first) > maximum:
        first = first[: maximum - 1].rsplit(" ", 1)[0] + "…"
    return first if first.endswith((".", "!", "?", "…")) else first + "."


def _plain_language(value: Any) -> str:
    """Remove internal evaluation vocabulary while preserving a candid meaning."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    replacements = (
        (r"\bstrongly adjacent\b", "closely related"),
        (r"\badjacent\b", "closely related"),
        (r"\btransferable\b", "relevant"),
        (r"\bdirect evidence\b", "demonstrated experience"),
        (r"\bevidence profile\b", "career history"),
        (r"\bcapability graph\b", "career history"),
        (r"\bevidence\b", "experience"),
        (r"\bprovenance\b", "source tracking"),
        (r"\bconfidence\b", "certainty"),
        (r"\bunsupported\b", "not yet demonstrated"),
        (r"\bselection score\b", "fit"),
        (r"\bhigh[- ]confidence\b", "well established"),
        (r"\blow[- ]confidence\b", "worth confirming"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def _recommendation(
    match_report: dict[str, Any], alignment_matrix: list[dict[str, Any]]
) -> dict[str, Any]:
    score = match_report.get("match_score")
    if score is None:
        return {
            "match_label": "Analysis Incomplete",
            "recommendation": "Consider",
            "recommended_next_step": "Complete the role analysis before deciding whether to apply.",
        }
    score = int(score)
    hard_gaps = [
        row for row in alignment_matrix
        if row.get("requirement_type") == "Hard Gate"
        and row.get("alignment_level") == "Unsupported"
    ]
    material_gaps = list(match_report.get("material_fit_gaps") or [])
    configured_action = str(match_report.get("recommended_action") or "")
    if configured_action == "Pass" or score < 55:
        recommendation = "Probably Skip"
    elif score < 70:
        recommendation = "Consider"
    elif score < 85:
        recommendation = "Apply"
    else:
        recommendation = "Apply Immediately"
    if hard_gaps:
        recommendation = "Probably Skip" if len(hard_gaps) >= 2 else "Consider"
    elif len(material_gaps) >= 2 and recommendation == "Apply Immediately":
        recommendation = "Apply"

    if recommendation == "Apply Immediately":
        match_label = "Strong Match — Apply"
        next_step = "Generate Materials"
    elif recommendation == "Apply":
        match_label = (
            "Strong Match — Apply" if score >= 85 else "Good Match — Apply"
        )
        next_step = "Generate Materials"
    elif recommendation == "Consider":
        match_label = "Strategic Stretch — Consider"
        next_step = "Review the open questions, then decide whether to generate materials."
    else:
        match_label = "Limited Match — Probably Skip"
        next_step = "Skip or save this role unless the tradeoffs are intentional."
    return {
        "match_label": match_label,
        "recommendation": recommendation,
        "recommended_next_step": next_step,
        "hard_requirement_gap_count": len(hard_gaps),
    }


def _why_match(selection: dict[str, Any]) -> list[dict[str, str]]:
    selected = [
        item
        for field in ("primary_evidence", "supporting_evidence")
        for item in selection.get(field) or []
        if isinstance(item, dict)
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        category = str(item.get("category") or "Professional Experience")
        heading = THEME_HEADINGS.get(category, category)
        grouped.setdefault(heading, []).append(item)
    themes: list[dict[str, str]] = []
    for heading, items in grouped.items():
        descriptions: list[str] = []
        seen_descriptions: set[str] = set()
        for item in items:
            description = _sentence(item.get("description"))
            key = description.lower()
            if description and key not in seen_descriptions:
                seen_descriptions.add(key)
                descriptions.append(description)
        explanation = " ".join(descriptions[:2])
        if heading == "AI Product and Workflow Leadership" and items:
            explanation = (
                "You conceived and directed iterative development of an AI-enabled career "
                "intelligence product, including role interpretation, evaluation, workflow "
                "automation, quality safeguards, and user review controls."
            )
        if not explanation:
            titles = ", ".join(str(item.get("title")) for item in items[:3])
            explanation = f"Your experience with {titles} maps well to this role."
        themes.append(
            {"heading": heading, "explanation": _plain_language(explanation)}
        )
    return themes[:5]


def _emphasis(themes: list[dict[str, str]], selection: dict[str, Any]) -> list[str]:
    selected = [
        item
        for field in ("primary_evidence", "supporting_evidence")
        for item in selection.get(field) or []
        if isinstance(item, dict)
    ]
    priorities = []
    for theme in themes:
        related_titles = [
            str(item.get("title"))
            for item in selected
            if THEME_HEADINGS.get(
                str(item.get("category") or "Professional Experience"),
                str(item.get("category") or "Professional Experience"),
            ) == theme["heading"]
        ][:3]
        detail = f", especially {', '.join(related_titles)}" if related_titles else ""
        priorities.append(f"Lead with your {theme['heading'].lower()} experience{detail}.")
    return priorities[:6]


def _discussion_topics(
    match_report: dict[str, Any], selection: dict[str, Any]
) -> list[str]:
    gap_values: list[Any] = [
        *(match_report.get("material_fit_gaps") or []),
        *(match_report.get("match_gaps") or []),
    ]
    for gap in selection.get("known_gaps") or []:
        if isinstance(gap, dict):
            requirement = str(gap.get("requirement") or "").strip()
            reason = str(gap.get("reason") or "").strip()
            if requirement:
                requirement_text = requirement.lower().rstrip(".")
                prefix = (
                    "Be prepared to discuss how you "
                    if re.match(r"^(partner|lead|manage|build|design|own)\b", requirement_text)
                    else "Be prepared to discuss "
                )
                gap_values.append(f"{prefix}{requirement_text}. {reason}")
            else:
                gap_values.append(reason)
    topics = []
    for value in _dedupe(gap_values):
        clean = _plain_language(value)
        direct_gap = re.match(
            r"demonstrated experience is not established for:\s*(.+)",
            clean,
            flags=re.I,
        )
        keep_two_sentences = bool(direct_gap)
        if direct_gap:
            clean = (
                "This role may probe more deeply on "
                + direct_gap.group(1).rstrip(".")
                + ". Prepare the closest examples you have and keep the scope clear."
            )
        clean = re.sub(r"\byou lack\b", "your background is less focused on", clean, flags=re.I)
        clean = re.sub(r"\bno experience\b", "less demonstrated experience", clean, flags=re.I)
        if clean:
            topics.append(clean if keep_two_sentences else _sentence(clean))
    return topics[:3]


def build_hiring_manager_brief(
    match_report: dict[str, Any],
    selection: dict[str, Any],
    hiring_manager_lens: dict[str, Any] | None = None,
    application_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a persisted user-facing brief without an LLM call."""
    matrix = list((match_report.get("capability_graph") or {}).get("alignment_matrix") or [])
    recommendation = _recommendation(match_report, matrix)
    themes = _why_match(selection)
    score = match_report.get("match_score")
    summary = _plain_language(match_report.get("match_summary") or "")
    if not summary:
        summary = (
            "Your experience aligns with several of the role's most important needs."
            if score is not None and int(score) >= 70
            else "This role has useful points of alignment, alongside tradeoffs to review."
        )
    topics = _discussion_topics(match_report, selection)
    return {
        "brief_version": BRIEF_VERSION,
        "generated_at": _now(),
        "match_recommendation": recommendation["match_label"],
        "recommendation": recommendation["recommendation"],
        "match_summary": _sentence(summary, 420),
        "why_match": themes,
        "what_to_emphasize": _emphasis(themes, selection),
        "what_to_discuss": topics,
        "recommended_next_step": recommendation["recommended_next_step"],
        "grounding": {
            "selected_evidence_ids": list(selection.get("selected_evidence_ids") or []),
            "selected_evidence_count": len(selection.get("selected_evidence_ids") or []),
            "requirement_count": len(matrix),
            "hard_requirement_gap_count": recommendation.get("hard_requirement_gap_count", 0),
        },
        "advanced": {
            "relevant_capabilities": list(selection.get("important_capabilities") or []),
            "manual_overrides": dict(selection.get("overrides") or {}),
            "hiring_problem": str((hiring_manager_lens or {}).get("hiring_problem") or ""),
            "positioning": str((application_strategy or {}).get("candidate_positioning") or ""),
        },
    }


def default_brief_contains_internal_language(brief: dict[str, Any]) -> list[str]:
    """Return internal terms found in fields rendered by the default brief."""
    visible = " ".join(
        [
            str(brief.get("match_recommendation") or ""),
            str(brief.get("recommendation") or ""),
            str(brief.get("match_summary") or ""),
            *(str(item.get("heading") or "") + " " + str(item.get("explanation") or "") for item in brief.get("why_match") or [] if isinstance(item, dict)),
            *(str(value) for value in brief.get("what_to_emphasize") or []),
            *(str(value) for value in brief.get("what_to_discuss") or []),
            str(brief.get("recommended_next_step") or ""),
        ]
    ).lower()
    return [term for term in DEFAULT_INTERNAL_TERMS if term in visible]


def brief_card_summary(record: dict[str, Any]) -> dict[str, str]:
    """Return the small persisted subset suitable for a dashboard card."""
    brief = record.get("hiring_manager_brief")
    brief = dict(brief) if isinstance(brief, dict) else {}
    return {
        "match_recommendation": str(
            brief.get("match_recommendation")
            or record.get("match_tier")
            or "Analysis needed"
        ),
        "reason": str(
            brief.get("match_summary")
            or record.get("match_summary")
            or "Refresh the role analysis for a concise recommendation."
        ),
        "recommendation": str(
            brief.get("recommendation")
            or record.get("recommended_action")
            or "Consider"
        ),
        "next_action": str(
            brief.get("recommended_next_step")
            or record.get("next_action")
            or "Review the role"
        ),
    }
