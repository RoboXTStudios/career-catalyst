"""Deterministic, shared role-intent classification and generation guidance."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import re
import yaml

try:
    from .candidate_output import humanize_identifier, humanize_values
    from .filename_utils import company_display_name
except ImportError:
    from candidate_output import humanize_identifier, humanize_values
    from filename_utils import company_display_name


DEFAULT_ARCHETYPE = "general_operations"
ROLE_INTENT_RULES_PATH = Path("config/role_intent_rules.yml")
SOURCE_ROLE_INTENT_RULES_PATH = Path(__file__).resolve().parents[1] / ROLE_INTENT_RULES_PATH


def load_role_intent_rules(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else Path.cwd()
    candidates = (SOURCE_ROLE_INTENT_RULES_PATH, root / ROLE_INTENT_RULES_PATH)
    rules_path = next((path for path in candidates if path.is_file()), None)
    if rules_path is None:
        raise FileNotFoundError("config/role_intent_rules.yml was not found in code or runtime roots")
    loaded = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    rules = loaded.get("role_intent") if isinstance(loaded, dict) else None
    if not isinstance(rules, dict) or not isinstance(rules.get("archetypes"), dict):
        raise ValueError("config/role_intent_rules.yml must contain role_intent.archetypes")
    return rules


def _role_text(role: Mapping[str, Any]) -> str:
    values = (
        role.get("job_title"),
        role.get("title"),
        role.get("role"),
        role.get("raw_text"),
        role.get("job_description"),
        " ".join(str(value) for value in role.get("keywords", []) if value),
        " ".join(str(value) for value in role.get("responsibilities", []) if value),
        " ".join(str(value) for value in role.get("qualifications", []) if value),
    )
    return re.sub(r"\s+", " ", " ".join(str(value or "") for value in values)).lower()


def _contains(text: str, phrase: str) -> bool:
    phrase = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _seniority(role: Mapping[str, Any]) -> str:
    title = str(role.get("job_title") or role.get("title") or role.get("role") or "").lower()
    for label, terms in (
        ("executive", ("chief", "vice president", "vp", "head of")),
        ("director", ("director",)),
        ("senior_manager", ("senior manager", "sr. manager", "sr manager")),
        ("manager", ("manager",)),
        ("senior_individual_contributor", ("senior", "lead", "principal")),
    ):
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", title) for term in terms):
            return label
    return "unspecified"


def _score_archetype(
    text: str,
    rule: Mapping[str, Any],
    weights: Mapping[str, Any],
) -> tuple[int, list[tuple[int, str]]]:
    matches: list[tuple[int, str]] = []
    signals = rule.get("signals") or {}
    for tier in ("action_outcome", "supporting", "generic"):
        weight = int(weights.get(tier, 0))
        for phrase in signals.get(tier, []) or []:
            if _contains(text, str(phrase)):
                matches.append((weight, str(phrase)))
    matches.sort(key=lambda item: (-item[0], item[1].lower()))
    return sum(weight for weight, _phrase in matches), matches


def _confidence(best_score: int, second_score: int, threshold: int) -> str:
    if best_score >= max(18, threshold * 2) and best_score - second_score >= 4:
        return "high"
    if best_score >= threshold:
        return "medium"
    return "low"


def _greeting(company: Any) -> str:
    display = company_display_name(company).strip()
    if display.lower() in {"", "company", "unknown", "unknown company", "not provided"}:
        return "Dear Hiring Team,"
    return f"Dear {display} Hiring Team,"


def build_role_intent(
    role: Mapping[str, Any],
    project_root: str | Path | None = None,
    *,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one inspectable Role Intent Profile from action-and-outcome signals."""
    configured = dict(rules or load_role_intent_rules(project_root))
    archetypes = configured["archetypes"]
    weights = configured.get("score_weights") or {}
    threshold = int(configured.get("specialized_threshold", 9))
    secondary_threshold = int(configured.get("secondary_threshold", 6))
    text = _role_text(role)
    ranked: list[tuple[int, str, list[tuple[int, str]]]] = []
    for archetype, rule in archetypes.items():
        if archetype == DEFAULT_ARCHETYPE:
            continue
        score, matches = _score_archetype(text, rule, weights)
        ranked.append((score, str(archetype), matches))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_archetype, best_matches = ranked[0] if ranked else (0, DEFAULT_ARCHETYPE, [])
    if best_score < threshold:
        primary = DEFAULT_ARCHETYPE
        selected_matches = best_matches
        confidence = "low" if best_score < max(1, threshold // 2) else "medium"
    else:
        primary = best_archetype
        selected_matches = best_matches
        second_score = ranked[1][0] if len(ranked) > 1 else 0
        confidence = _confidence(best_score, second_score, threshold)
    secondary = [
        archetype
        for score, archetype, _matches in ranked
        if archetype != primary and score >= secondary_threshold and score >= best_score * 0.5
    ][:3]
    rule = deepcopy(archetypes[primary])
    resume = deepcopy(rule.get("resume") or {})
    cover_letter = deepcopy(rule.get("cover_letter") or {})
    resume.setdefault("headline_profile", resume.pop("headline", ""))
    if "headline" in resume:
        resume.pop("headline")
    resume.setdefault("summary_profile", resume.pop("summary", ""))
    if "summary" in resume:
        resume.pop("summary")
    resume.setdefault("competency_profile", primary)
    resume.setdefault("tools_profile", primary)
    cover_letter["greeting"] = _greeting(role.get("company"))
    return {
        "primary_archetype": primary,
        "secondary_archetypes": secondary,
        "confidence": confidence,
        "seniority": _seniority(role),
        "business_environment": secondary + [primary],
        "primary_hiring_need": str(rule.get("primary_hiring_need") or ""),
        "required_outcomes": list(rule.get("required_outcomes") or []),
        "work_motions": list(rule.get("work_motions") or []),
        "reasoning_signals": [phrase for _weight, phrase in selected_matches[:12]],
        "lead_evidence": list(rule.get("lead_evidence") or []),
        "supporting_evidence": list(rule.get("supporting_evidence") or []),
        "suppressed_evidence": list(rule.get("suppressed_evidence") or []),
        "resume": resume,
        "cover_letter": cover_letter,
        "scores": {archetype: score for score, archetype, _matches in ranked},
    }


def role_intent_snapshot(role_intent: Mapping[str, Any]) -> dict[str, Any]:
    resume = role_intent.get("resume") or {}
    cover = role_intent.get("cover_letter") or {}
    return {
        "primary_archetype": role_intent.get("primary_archetype"),
        "secondary_archetypes": list(role_intent.get("secondary_archetypes") or []),
        "confidence": role_intent.get("confidence"),
        "primary_hiring_need": role_intent.get("primary_hiring_need"),
        "required_outcomes": list(role_intent.get("required_outcomes") or []),
        "reasoning_signals": list(role_intent.get("reasoning_signals") or []),
        "lead_evidence": list(role_intent.get("lead_evidence") or []),
        "supporting_evidence": list(role_intent.get("supporting_evidence") or []),
        "suppressed_evidence": list(role_intent.get("suppressed_evidence") or []),
        "headline_profile": resume.get("headline_profile"),
        "earlier_career_policy": resume.get("earlier_career_policy"),
        "selected_project_limit": resume.get("selected_project_limit"),
        "target_max_pages": resume.get("target_max_pages"),
        "primary_cover_letter_story": cover.get("primary_story"),
        "secondary_cover_letter_story": cover.get("secondary_story"),
        "generated_greeting": cover.get("greeting"),
    }


def tailoring_plan(role_intent: Mapping[str, Any]) -> dict[str, Any]:
    resume = role_intent.get("resume") or {}
    return {
        "detected_role": humanize_identifier(role_intent.get("primary_archetype") or DEFAULT_ARCHETYPE),
        "primary_hiring_need": role_intent.get("primary_hiring_need"),
        "leading_with": humanize_values(role_intent.get("lead_evidence") or []),
        "supporting_with": humanize_values(role_intent.get("supporting_evidence") or []),
        "de_emphasizing": humanize_values(role_intent.get("suppressed_evidence") or []),
        "earlier_career": humanize_identifier(resume.get("earlier_career_policy")),
        "selected_projects": humanize_values(resume.get("selected_project_ids") or []),
        "target_resume_length": f"{int(resume.get('target_max_pages') or 2)} pages maximum",
        "confidence": str(role_intent.get("confidence") or "low").title(),
        "matched_signals": humanize_values(role_intent.get("reasoning_signals") or []),
    }
