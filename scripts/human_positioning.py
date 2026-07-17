"""Shared human-positioning rules for generated career materials."""

from __future__ import annotations

import re
from typing import Any, Sequence

try:
    from .role_lens import classify_role_lens
except ImportError:
    from role_lens import classify_role_lens


TENURE_FORWARD_PATTERNS = (
    r"\b\d{1,2}\+?\s+years?\s+of\s+experience\b",
    r"\bover\s+(?:two|three|four)\s+decades\b",
    r"\bmore\s+than\s+(?:two|three|four)\s+decades\b",
    r"\bdecades?\s+of\s+experience\b",
    r"\blong-standing\s+career\b",
    r"\blong[- ]term\s+hands[- ]on\s+experience\b",
    r"\bdating\s+back\s+to\s+the\s+(?:19|20)\d0s\b",
)

POSITIONING_CLICHES = (
    "seasoned professional",
    "veteran",
    "extensive experience",
    "results-driven",
    "results driven",
    "proven track record",
    "proven record",
    "dynamic leader",
    "accomplished executive",
    "highly accomplished",
)
PERSONAL_PROJECT_TERMS = ("Career Catalyst", "CampaignOS", "Substack")


PROFILE_SUMMARIES = {
    "people_operations": (
        "Operations leader known for improving how cross-functional teams communicate, understand "
        "ownership, and adopt practical ways of working. Builds clear workflows, usable standards, "
        "and dependable communication practices that reduce day-to-day friction while helping teams "
        "execute business priorities with confidence."
    ),
    "executive_operations": (
        "Operations leader known for finding the real constraint in complex work and turning it into "
        "clear decisions, usable systems, and dependable delivery. Connects business operations, "
        "workflow governance, cross-functional collaboration, and practical process design to reduce "
        "ambiguity and help teams move with confidence."
    ),
    "entertainment_marketing": (
        "Entertainment marketing operator who brings creative, media, analytics, technology, and "
        "operations partners into a shared way of working. Builds practical workflows, quality "
        "standards, and reporting systems that make high-volume campaign work easier to coordinate "
        "without losing sight of the audience or the creative idea."
    ),
    "music_industry": (
        "Music and entertainment operator with an editorial eye and a systems mindset. Known for "
        "turning audience, content, and partnership goals into clear workflows, thoughtful stories, "
        "and repeatable ways of working that protect both quality and human voice."
    ),
    "product_ai": (
        "Product-minded operations leader who turns recurring friction into useful workflows, "
        "validation rules, and decision tools. Works from the problem outward, combining "
        "structured discovery, hands-on systems design, governance, and human judgment to make "
        "complex work easier to run."
    ),
    "google_youtube_operations": (
        "Strategy and operations leader known for translating Google and YouTube platform capabilities "
        "into advertiser activation, measurement readiness, and workable cross-functional routines. "
        "Connects brand goals, product feedback, campaign operations, and governance to make "
        "adoption clearer and execution more measurable."
    ),
}


class HumanPositioningError(ValueError):
    """Raised when generated narrative copy violates human-positioning rules."""


def positioning_violations(text: str) -> list[str]:
    """Return tenure-forward or clichéd claims found in narrative copy."""
    value = str(text or "")
    lowered = value.lower()
    violations = [
        pattern
        for pattern in TENURE_FORWARD_PATTERNS
        if re.search(pattern, value, flags=re.IGNORECASE)
    ]
    violations.extend(phrase for phrase in POSITIONING_CLICHES if phrase in lowered)
    return violations


def validate_human_positioning(text: str, artifact: str) -> None:
    """Reject narrative copy that leads with tenure or unsupported prestige language."""
    violations = positioning_violations(text)
    if violations:
        raise HumanPositioningError(
            f"Generated {artifact} contains tenure-forward or clichéd positioning: {violations[0]}"
        )


def personal_project_violations(text: str) -> list[str]:
    """Return personal-project names that leaked into applicant-facing copy."""
    lowered = str(text or "").lower()
    return [term for term in PERSONAL_PROJECT_TERMS if term.lower() in lowered]


def validate_applicant_evidence(text: str, artifact: str) -> None:
    """Reject applicant-facing copy that references disabled personal projects."""
    violations = personal_project_violations(text)
    if violations:
        raise HumanPositioningError(
            f"Generated {artifact} contains disabled personal-project evidence: {violations[0]}"
        )


def replace_personal_project_paragraphs(text: str, replacement: str) -> str:
    """Replace project-led paragraphs with one verified professional evidence paragraph."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    cleaned: list[str] = []
    replacement_used = False
    for paragraph in paragraphs:
        if personal_project_violations(paragraph):
            if replacement and not replacement_used:
                cleaned.append(replacement.strip())
                replacement_used = True
            continue
        cleaned.append(paragraph)
    return "\n\n".join(cleaned)


def professional_summary(
    resume_profile: str,
    parsed_job: dict[str, Any],
    competencies: Sequence[str] = (),
) -> str:
    """Build an identity/approach/outcome summary while ATS terms remain in competencies."""
    role_lens = classify_role_lens(parsed_job)
    profile_key = (
        "people_operations"
        if role_lens["primary"] == "people_operations"
        else
        "google_youtube_operations"
        if "youtube" in " ".join(
            str(parsed_job.get(key) or "") for key in ("job_title", "company", "raw_text")
        ).lower()
        and "google" in " ".join(
            str(parsed_job.get(key) or "") for key in ("job_title", "company", "raw_text")
        ).lower()
        else resume_profile
    )
    summary = PROFILE_SUMMARIES.get(profile_key, PROFILE_SUMMARIES["executive_operations"])
    validate_human_positioning(summary, "professional summary")
    return summary


def evidence_capability_score(card: dict[str, Any]) -> int:
    """Reward demonstrated capability and penalize tenure/prestige-only positioning."""
    proof_text = " ".join(
        [
            str(card.get("short_description") or ""),
            " ".join(str(point) for point in card.get("proof_points", [])),
            " ".join(str(tag).replace("_", " ") for tag in card.get("tags", [])),
        ]
    ).lower()
    signal_groups = (
        (5, ("measurable impact", "60+", "400+", "%", "$")),
        (5, ("systems built", "built", "designed", "developed", "created")),
        (4, ("cross-functional", "cross functional")),
        (4, ("ai workflow", "ai-enabled", "ai-powered", "automation")),
        (3, ("governance", "quality assurance", "qa", "validation")),
        (3, ("ambiguity reduction", "clarity", "decision", "risk visibility")),
        (2, ("interesting project", "builder", "platform", "publication")),
    )
    score = sum(weight for weight, signals in signal_groups if any(signal in proof_text for signal in signals))
    score -= 5 * sum(
        phrase in proof_text
        for phrase in (
            "years of experience",
            "decades of experience",
            "seasoned",
            "veteran",
            "proven leader",
            "executive leader",
            "senior leader",
        )
    )
    return score
