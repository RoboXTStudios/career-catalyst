"""Persisted, human-readable career strategy built from saved prospect analysis."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from .application_tracker import get_record_status, is_archived
except ImportError:
    from application_tracker import get_record_status, is_archived


CAREER_COACH_VERSION = 1
VERIFIED_STATES = {"verified", "user confirmed", "high confidence"}
THEME_LABELS = {
    "Campaign Operations": "operational leadership",
    "People Leadership": "team development and people leadership",
    "Cross-functional Leadership": "cross-functional leadership",
    "Advertising Technology": "advertising-platform expertise",
    "Platform Implementation": "platform implementation",
    "Programmatic": "programmatic advertising fluency",
    "Technical Troubleshooting": "technical problem solving",
    "QA": "quality assurance and governance",
    "Measurement": "measurement readiness",
    "Launch Readiness": "launch readiness",
    "Workflow Design": "workflow design",
    "Product Collaboration": "product thinking",
    "Transformation": "operational transformation",
    "Governance": "governance and consistency",
    "AI Systems": "AI-enabled workflow design",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any, maximum: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -:;.")
    if len(text) > maximum:
        text = text[: maximum - 1].rsplit(" ", 1)[0] + "…"
    return text


def _sentence(value: Any, maximum: int = 320) -> str:
    text = _clean(value, maximum)
    return text if not text or text.endswith((".", "!", "?", "…")) else text + "."


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _selected_evidence(application: dict[str, Any]) -> list[dict[str, Any]]:
    selection = application.get("role_evidence_selection") or {}
    if not isinstance(selection, dict):
        return []
    selected = [
        item
        for field in ("primary_evidence", "supporting_evidence")
        for item in (selection.get(field) or [])
        if isinstance(item, dict)
    ]
    return [
        item
        for item in selected
        if _clean(item.get("verification_status") or item.get("evidence_type")).lower()
        in VERIFIED_STATES
    ]


def career_coach_source_fingerprint(application: dict[str, Any]) -> str:
    """Fingerprint only persisted fields that materially change coaching advice."""
    selection = application.get("role_evidence_selection") or {}
    selected = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "description": item.get("description"),
            "verification_status": item.get("verification_status"),
            "updated_at": item.get("updated_at") or item.get("last_updated"),
        }
        for field in ("primary_evidence", "supporting_evidence")
        for item in (selection.get(field) or [])
        if isinstance(item, dict)
    ] if isinstance(selection, dict) else []
    strategy = application.get("application_strategy") or {}
    strategy_source = {
        key: strategy.get(key)
        for key in (
            "primary_hiring_problem",
            "candidate_positioning",
            "material_gaps",
            "must_prove",
            "must_not_claim",
            "resume_emphasis",
            "cover_letter_thesis",
            "interview_positioning",
            "application_recommendation",
        )
    } if isinstance(strategy, dict) else {}
    payload = {
        "id": application.get("id"),
        "company": application.get("company"),
        "role": application.get("role"),
        "status": get_record_status(application),
        "is_archived": is_archived(application),
        "context_fingerprint": application.get("context_fingerprint"),
        "prospect_revision": application.get("prospect_revision"),
        "match_summary": application.get("match_summary"),
        "match_gaps": application.get("match_gaps") or [],
        "role_interpretation": application.get("role_interpretation") or {},
        "application_strategy": strategy_source,
        "selected_evidence": selected,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def career_coach_is_stale(
    application: dict[str, Any], brief: dict[str, Any] | None = None
) -> bool:
    saved = brief if isinstance(brief, dict) else application.get("career_coach_brief")
    return bool(
        not isinstance(saved, dict)
        or not saved
        or saved.get("source_fingerprint") != career_coach_source_fingerprint(application)
        or int(saved.get("brief_version") or 0) != CAREER_COACH_VERSION
    )


def _themes(evidence: list[dict[str, Any]]) -> list[str]:
    values = []
    for item in evidence:
        category = _clean(item.get("category"))
        values.append(THEME_LABELS.get(category, category or item.get("title")))
    return _dedupe(values)[:4]


def _positioning(application: dict[str, Any], themes: list[str]) -> str:
    interpretation = application.get("role_interpretation") or {}
    archetype = _clean(
        interpretation.get("primary_archetype")
        or application.get("role_family")
        or "operations"
    ).lower()
    mission = _clean(interpretation.get("core_mission"), 180)
    strengths = " and ".join(themes[:2]) or "cross-functional operating leadership"
    ending = f" to {mission[0].lower() + mission[1:]}" if mission else ""
    return _sentence(
        f"Position yourself as a senior {archetype} leader who brings {strengths}{ending}",
        360,
    )


def _downplay(application: dict[str, Any], themes: list[str]) -> list[str]:
    selection = application.get("role_evidence_selection") or {}
    excluded = selection.get("excluded_evidence") or [] if isinstance(selection, dict) else []
    selected_keys = " ".join(themes).lower()
    values = []
    for item in excluded:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"))
        category = _clean(item.get("category"))
        if not title or title.lower() in selected_keys or category.lower() in selected_keys:
            continue
        values.append(f"Mention briefly, but do not lead with {title.lower()} unless it connects directly to the interviewer’s priorities.")
    return _dedupe(values)[:3]


def _concerns(application: dict[str, Any]) -> list[str]:
    selection = application.get("role_evidence_selection") or {}
    gap_values: list[Any] = list(application.get("match_gaps") or [])
    if isinstance(selection, dict):
        gap_values.extend(
            item.get("requirement")
            for item in selection.get("known_gaps") or []
            if isinstance(item, dict)
        )
    concerns = []
    for value in _dedupe(gap_values):
        concerns.append(
            _sentence(
                f"The hiring manager may want clearer proof of {_clean(value).lower()}",
                300,
            )
        )
    return concerns[:4]


def _responses(
    concerns: list[str], evidence: list[dict[str, Any]]
) -> list[dict[str, str]]:
    proof = evidence[: max(1, len(concerns))]
    responses = []
    for index, concern in enumerate(concerns):
        item = proof[index % len(proof)] if proof else {}
        title = _clean(item.get("title"))
        description = _sentence(item.get("description"), 230)
        if title and description:
            strategy = (
                f"Be direct about the exact scope, then use {title} as the closest verified example: {description}"
            )
        else:
            strategy = (
                "Acknowledge the boundary clearly, answer with the closest verified experience, and ask how much depth the role requires."
            )
        responses.append({"concern": concern, "response_strategy": _sentence(strategy, 360)})
    return responses


def _stories(evidence: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    stories = []
    for item in evidence[:4]:
        title = _clean(item.get("title"))
        company = _clean(item.get("company") or item.get("career_period"))
        source_role = _clean(item.get("role"))
        description = _sentence(item.get("description"), 340)
        task = _sentence(item.get("leadership_scope") or item.get("subcategory"), 220)
        if not title or not description:
            continue
        stories.append(
            {
                "title": title,
                "why_it_matters": _sentence(f"This shows experience relevant to {role}"),
                "angle_to_emphasize": _sentence(
                    item.get("positioning_emphases", [None])[0]
                    if isinstance(item.get("positioning_emphases"), list)
                    and item.get("positioning_emphases")
                    else item.get("leadership_scope") or title
                ),
                "star": {
                    "situation": _sentence(
                        " — ".join(value for value in (company, source_role) if value)
                        or "Use the saved career context for this example"
                    ),
                    "task": task or _sentence(f"Deliver the work represented by {title}"),
                    "action": description,
                    "result": "No separate measurable result is recorded; describe only the verified qualitative outcome.",
                },
            }
        )
    return stories


def _questions_to_prepare(application: dict[str, Any]) -> list[str]:
    interpretation = application.get("role_interpretation") or {}
    role = _clean(application.get("role") or "this role")
    mission = _clean(interpretation.get("core_mission") or role, 160)
    must_haves = _dedupe(interpretation.get("true_must_haves") or [])
    questions = [
        f"How have you led through ambiguity while working toward this kind of mission: {mission}?",
        f"Tell me about a time you aligned several stakeholders around a difficult decision relevant to {role}.",
        "How do you balance strategic judgment with hands-on operational follow-through?",
        "Describe a process you improved and how you knew the change was working.",
        "How do you develop teams while maintaining delivery quality?",
    ]
    questions.extend(f"What experience best demonstrates: {_clean(value, 180)}?" for value in must_haves[:3])
    return _dedupe(questions)[:8]


def _questions_for_them(application: dict[str, Any]) -> list[str]:
    interpretation = application.get("role_interpretation") or {}
    mission = _clean(interpretation.get("core_mission") or application.get("role"), 170)
    stakeholders = _clean(interpretation.get("primary_customer_or_stakeholder"), 130)
    measures = _dedupe(interpretation.get("success_metrics") or [])
    questions = [
        f"What would meaningful progress on {mission.lower()} look like in the first six months?",
        f"Where does this role have final decision authority, and where does it need alignment{f' with {stakeholders}' if stakeholders else ''}?",
        "Which operating problems are creating the most friction for the team today?",
        "How is the team structured, and what leadership behavior would help it perform at its best?",
    ]
    if measures:
        questions.append(f"How do you currently measure success around {_clean(measures[0], 160).lower()}?")
    questions.append("What tends to distinguish people who build trust quickly across this organization?")
    return _dedupe(questions)[:6]


def _next_action(application: dict[str, Any]) -> str:
    status = get_record_status(application)
    if is_archived(application):
        return "No action required; keep this role in the archive unless circumstances change."
    if status == "Drafted":
        return "Review this positioning and generate the application package."
    if status == "Applied":
        return "Prepare for a recruiter screen and monitor the saved follow-up timing."
    if status == "Under Consideration":
        return "Prepare for the next conversation and respond to any open employer request."
    if status == "Interviewing":
        return "Use the story outlines to prepare for the next interview."
    if status == "Offer":
        return "Evaluate the offer against the role scope, authority, team, and success measures."
    return "Move to the archive or restore the role only if the opportunity reopens."


def build_career_coach_brief(application: dict[str, Any]) -> dict[str, Any]:
    """Build concise coaching from already-persisted, verified prospect information."""
    evidence = _selected_evidence(application)
    themes = _themes(evidence)
    concerns = _concerns(application)
    role = _clean(application.get("role") or "this role")
    return {
        "brief_version": CAREER_COACH_VERSION,
        "generated_at": _now(),
        "source_fingerprint": career_coach_source_fingerprint(application),
        "source_revision": int(application.get("prospect_revision") or 0),
        "recommended_positioning": _positioning(application, themes),
        "lead_with": themes or ["the strongest verified experience that maps to the role’s core mission"],
        "downplay": _downplay(application, themes),
        "hiring_manager_concerns": concerns,
        "concern_responses": _responses(concerns, evidence),
        "best_stories": _stories(evidence, role),
        "questions_to_prepare_for": _questions_to_prepare(application),
        "questions_to_ask_them": _questions_for_them(application),
        "next_best_action": _next_action(application),
        "supporting_references": [
            {"id": item.get("id"), "title": item.get("title")}
            for item in evidence
            if item.get("id")
        ],
    }
