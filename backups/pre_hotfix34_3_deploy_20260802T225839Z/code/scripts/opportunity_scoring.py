"""Score Career Catalyst prospects against Trisha's stated search priorities."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from .job_freshness import detect_job_freshness
    from .parse_job import normalize_compensation
except ImportError:
    from job_freshness import detect_job_freshness
    from parse_job import normalize_compensation


WEIGHTS = {
    "Resume Fit": 0.22,
    "Salary Fit": 0.12,
    "Industry Alignment": 0.14,
    "Role Level Fit": 0.15,
    "Location Fit": 0.10,
    "Mission / Personal Alignment": 0.08,
    "Posting Freshness": 0.09,
    "Interview Probability": 0.10,
}


def _bounded(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _salary_score(value: Any) -> Optional[int]:
    compensation = normalize_compensation(value, source="saved")
    amounts = [
        float(amount)
        for amount in (compensation.get("minimum"), compensation.get("maximum"))
        if amount is not None
    ]
    if compensation.get("period") == "hour":
        amounts = [amount * 2080 for amount in amounts]
    if not amounts:
        return None
    maximum = max(amounts)
    minimum = min(amounts)
    if minimum >= 150000:
        return 100
    if maximum >= 180000:
        return 92
    if maximum >= 150000:
        return 84
    if maximum >= 130000:
        return 68
    if maximum >= 110000:
        return 45
    return 20


def _signal_score(text: str, groups: tuple[tuple[str, ...], ...], base: int = 35) -> int:
    matches = sum(1 for group in groups if any(signal in text for signal in group))
    return _bounded(base + (matches * ((100 - base) / max(1, len(groups)))))


def _industry_score(text: str) -> int:
    return _signal_score(
        text,
        (
            ("entertainment", "studio", "streaming", "media"),
            ("music", "record label", "publishing", "artist"),
            ("ai", "artificial intelligence", "automation", "workflow system"),
            ("live event", "touring", "venue", "ticketing"),
            ("creative technology", "product technology"),
        ),
        30,
    )


def _role_level_score(title: str, text: str) -> int:
    combined = f"{title} {text}".lower()
    if any(value in combined for value in ("vice president", " vp ", "head of", "director", "chief")):
        return 100
    if any(value in combined for value in ("senior lead", "principal", "senior manager", "staff ")):
        return 85
    if "senior" in combined or "lead" in title.lower():
        return 72
    if any(value in combined for value in ("coordinator", "assistant", "entry level", "junior")):
        return 20
    return 55


def _location_score(location: Any, text: str) -> int:
    combined = f"{location or ''} {text}".lower()
    if "los angeles" in combined or "remote" in combined:
        return 100
    if "hybrid" in combined or "southern california" in combined:
        return 92
    if "california" in combined:
        return 78
    if any(value in combined for value in ("new york", "onsite", "on-site", "in office")):
        return 42
    return 55


def score_opportunity(
    parsed_job: Dict[str, Any],
    match_report: Optional[Dict[str, Any]] = None,
    intelligence: Optional[Dict[str, Any]] = None,
    freshness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return weighted dimension scores and an action recommendation."""
    report = match_report or {}
    role_intelligence = intelligence or {}
    raw_text = str(parsed_job.get("raw_text") or "")
    lowered = raw_text.lower()
    freshness_result = freshness or detect_job_freshness(raw_text)
    resume_fit = _bounded(float(report.get("match_score") or 55))
    industry = _industry_score(lowered)
    role_level = _role_level_score(str(parsed_job.get("job_title") or ""), lowered)
    location = _location_score(parsed_job.get("location"), lowered)
    role_family = str(role_intelligence.get("role_family") or "")
    priority_terms = (
        "marketing operations", "business operations", "strategic operations",
        "ai workflow", "transformation", "process", "systems",
    )
    mission = _bounded(
        42
        + 10 * sum(term in lowered for term in priority_terms)
        + (10 if role_family in {"business_operations", "ai_operations_systems", "creative_marketing_ops", "product_strategy_ops"} else 0)
    )
    compensation = parsed_job.get("compensation") or normalize_compensation(
        parsed_job.get("salary_range"), source="saved"
    )
    salary = _salary_score(compensation)
    interview = _bounded((resume_fit * 0.5) + (industry * 0.2) + (role_level * 0.2) + (mission * 0.1))
    dimensions = {
        "Resume Fit": resume_fit,
        "Salary Fit": salary,
        "Industry Alignment": industry,
        "Role Level Fit": role_level,
        "Location Fit": location,
        "Mission / Personal Alignment": mission,
        "Posting Freshness": int(freshness_result["score"]),
        "Interview Probability": interview,
    }
    scored_weight = sum(
        WEIGHTS[key] for key, value in dimensions.items() if value is not None
    )
    overall = _bounded(
        sum(
            float(value) * WEIGHTS[key]
            for key, value in dimensions.items()
            if value is not None
        )
        / max(scored_weight, 0.01)
    )
    if freshness_result.get("is_closed"):
        recommendation = "Skip"
    elif overall >= 80:
        recommendation = "Apply Immediately"
    elif overall >= 65:
        recommendation = "Apply If Strategic"
    elif overall >= 50:
        recommendation = "Watch / Recheck"
    else:
        recommendation = "Skip"
    return {
        "overall_score": overall,
        "apply_recommendation": recommendation,
        "dimensions": dimensions,
        "salary_disclosed": bool(compensation.get("detected")),
        "compensation_disclosure_state": compensation.get("disclosure_state") or "unknown_unverified",
        "salary_verification_action": (
            "Verify compensation before recruiter screen."
            if not compensation.get("detected")
            else ""
        ),
    }
