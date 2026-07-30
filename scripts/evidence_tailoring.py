"""Deterministic, candidate-safe use of prospect-scoped Evidence projects."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "role", "that", "the", "their",
    "this", "to", "was", "were", "will", "with",
}


def project_title(project: Mapping[str, Any]) -> str:
    return str(project.get("title") or project.get("name") or "Untitled Evidence").strip()


def project_kind(project: Mapping[str, Any]) -> str:
    identity = " ".join(
        str(project.get(key) or "") for key in ("id", "title", "name")
    ).lower()
    if "career catalyst" in identity or "career_catalyst" in identity:
        return "career_catalyst"
    if "just for us" in identity or "podcast" in identity:
        return "podcast"
    return "other"


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _flatten(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten(nested)]
    return [str(value)] if value not in (None, "") else []


def _terms(value: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]+", " ".join(_flatten(value)).lower())
    return {word for word in words if len(word) > 2 and word not in STOP_WORDS}


def role_text(parsed_job: Mapping[str, Any]) -> str:
    return " ".join(
        _flatten(
            [
                parsed_job.get("job_title"),
                parsed_job.get("role"),
                parsed_job.get("raw_text"),
                parsed_job.get("job_description"),
                parsed_job.get("responsibilities"),
                parsed_job.get("qualifications"),
                parsed_job.get("keywords"),
            ]
        )
    ).lower()


def evidence_relevance(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> dict[str, Any]:
    """Return unique, posting-grounded Evidence matches without title repetition."""
    posting_terms = _terms(role_text(parsed_job))
    evidence_terms = _terms(
        [
            project.get("title"),
            project.get("problem"),
            project.get("actions"),
            project.get("results"),
            project.get("function"),
            project.get("project_type"),
            project.get("skills"),
            project.get("technologies"),
            project.get("tags"),
        ]
    )
    matched = sorted(posting_terms & evidence_terms)
    text = role_text(parsed_job)
    kind = project_kind(project)
    phrase_matches: list[str] = []
    if kind == "career_catalyst" and re.search(
        r"\b(product manager|product strategy|product operations|product requirements|roadmap)\b",
        text,
    ):
        phrase_matches.append("product development")
    if kind == "podcast" and any(
        phrase in text
        for phrase in ("podcast", "emerging format", "audio", "content lifecycle")
    ):
        phrase_matches.append("emerging audio formats")
    matched_signals = list(dict.fromkeys([*phrase_matches, *matched]))
    return {
        "score": len(matched) + (3 * len(phrase_matches)),
        "matched_signals": matched_signals[:10],
    }


def relevant_selected_evidence(
    projects: Sequence[Mapping[str, Any]],
    parsed_job: Mapping[str, Any],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, project in enumerate(projects):
        relevance = evidence_relevance(project, parsed_job)
        if int(relevance["score"]) <= 0:
            continue
        item = dict(project)
        item["_tailoring_relevance"] = relevance
        ranked.append((int(relevance["score"]), index, item))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item for _score, _index, item in ranked[: max(0, limit)]]


def _first_sentence(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    match = re.match(r"(.+?[.!?])(?:\s|$)", text)
    return (match.group(1) if match else text).strip()


def resume_project_bullets(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> list[str]:
    """Condense verified Evidence into one or two complete candidate-facing bullets."""
    corpus = " ".join(
        _flatten([project.get("problem"), project.get("actions"), project.get("results")])
    ).lower()
    kind = project_kind(project)
    if kind == "career_catalyst" and "product" in corpus:
        return [
            "Created and led development of an active AI-enabled career intelligence and application-operations product, defining product vision, requirements, priorities, workflows, acceptance criteria, and release guardrails.",
            "Built and iterated a tested local application integrating prospect evaluation, evidence selection, tailored materials, follow-up planning, interview preparation, status management, and role archiving.",
        ]
    if kind == "podcast" and re.search(r"\b(ten|10)[ -]episode", corpus):
        return [
            "Served as audio producer and editor for a ten-episode, multi-host podcast series released on Spotify, managing dialogue editing, pacing, audio quality, revisions, quality control, and release-ready delivery."
        ]
    bullets = [
        sentence
        for sentence in (
            _first_sentence(project.get("actions")),
            _first_sentence(project.get("results")),
        )
        if sentence
    ]
    return list(dict.fromkeys(bullets))[:2]


def cover_letter_project_paragraph(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> str:
    kind = project_kind(project)
    corpus = " ".join(_flatten(project)).lower()
    if kind == "career_catalyst" and "product" in corpus:
        return (
            "Through Career Catalyst, I am actively developing an AI-enabled career intelligence and "
            "application-operations product. I translate user needs into product vision, requirements, "
            "feature priorities, workflows, acceptance criteria, iterative testing, and release guardrails, "
            "hands-on work that connects product judgment with disciplined delivery."
        )
    if kind == "podcast" and re.search(r"\b(ten|10)[ -]episode", corpus):
        return (
            "I also served as audio producer and editor for Just for Us, a ten-episode, multi-host podcast "
            "series released on Spotify. I shaped pacing and episode flow, cleaned and balanced dialogue, "
            "managed revisions and quality control, and prepared each episode for release."
        )
    actions = _first_sentence(project.get("actions"))
    result = _first_sentence(project.get("results"))
    if not actions:
        return ""
    proof = f" {result}" if result and result != actions else ""
    return f"In {project_title(project)}, {actions[:1].lower() + actions[1:]}{proof}"


def evidence_score_contribution(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    before_score = int(before.get("match_score") or 0)
    after_score = int(after.get("match_score") or 0)
    matched = list(after.get("associated_evidence_matches") or [])
    return {
        "before": before_score,
        "after": after_score,
        "delta": after_score - before_score,
        "matched_requirements": matched,
        "explanation": (
            "No additional role requirements were matched by the selected Evidence."
            if not matched or after_score == before_score
            else "Selected Evidence matched additional verified role requirements."
        ),
    }


def output_use_metadata(
    selected_projects: Sequence[Mapping[str, Any]],
    *,
    system_recommended_projects: Sequence[str] = (),
    resume_projects_used: Sequence[str] = (),
    cover_letter_projects_used: Sequence[str] = (),
    score_contribution: Mapping[str, Any] | None = None,
    parsed_job: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = parsed_job or {}
    resume_used = list(dict.fromkeys(str(value) for value in resume_projects_used if value))
    cover_used = list(dict.fromkeys(str(value) for value in cover_letter_projects_used if value))
    used = set(resume_used) | set(cover_used)
    selected = []
    not_used = []
    for project in selected_projects:
        title = project_title(project)
        relevance = evidence_relevance(project, parsed)
        selected.append(
            {
                "id": str(project.get("id") or ""),
                "title": title,
                "manual": True,
                "relevance_score": int(relevance["score"]),
                "matched_signals": list(relevance["matched_signals"]),
            }
        )
        if title not in used:
            not_used.append(
                {
                    "id": str(project.get("id") or ""),
                    "title": title,
                    "reason": "No sufficiently specific role connection was found in the verified record.",
                }
            )
    return {
        "selected_evidence": selected,
        "system_recommended_projects": list(
            dict.fromkeys(str(value) for value in system_recommended_projects if value)
        ),
        "resume_projects_used": resume_used,
        "cover_letter_projects_used": cover_used,
        "projects_not_used": not_used,
        "evidence_score_contribution": dict(score_contribution or {}),
    }


def package_preview_fingerprint(
    prospect_id: str, evidence_project_ids: Sequence[Any]
) -> str:
    payload = {
        "prospect_id": str(prospect_id or "").strip(),
        "evidence_project_ids": [
            str(value).strip() for value in evidence_project_ids if str(value).strip()
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
