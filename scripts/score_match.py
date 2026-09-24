"""Score a parsed job description against Career Catalyst data."""

from datetime import date

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

try:
    from .application_tracker import (
        VALID_MATCH_ACTIONS,
        VALID_MATCH_CONFIDENCE,
        VALID_MATCH_TIERS,
    )
    from .load_data import DataLoadError
    from .resume_foundation import load_resume_foundation
    from .job_freshness import detect_job_freshness
    from .requirement_matching import match_evidence_to_requirements, requirement_coverage_bonus
    from .parse_job import (
        extract_keywords,
        extract_qualifications,
        extract_preferred_qualifications,
        extract_responsibilities,
        normalize_compensation,
        parse_job_description,
        _analysis_text,
        extract_metadata,
    )
except ImportError:
    from application_tracker import (
        VALID_MATCH_ACTIONS,
        VALID_MATCH_CONFIDENCE,
        VALID_MATCH_TIERS,
    )
    from load_data import DataLoadError
    from resume_foundation import load_resume_foundation
    from job_freshness import detect_job_freshness
    from requirement_matching import match_evidence_to_requirements, requirement_coverage_bonus
    from parse_job import (
        extract_keywords,
        extract_qualifications,
        extract_preferred_qualifications,
        extract_responsibilities,
        normalize_compensation,
        parse_job_description,
        _analysis_text,
        extract_metadata,
    )


GENERIC_TERMS = {
    "ability",
    "across",
    "company",
    "experience",
    "job",
    "management",
    "responsible",
    "role",
    "strong",
    "support",
    "team",
    "teams",
    "work",
    "working",
}

# Candidate-facing Evidence diagnostics are derived from semantic requirements,
# not arbitrary one-word overlap. Numeric keyword contribution remains separate,
# with common-word noise excluded before either candidate or Evidence matching.
RESUME_PROFILE_KEYWORDS = {
    "executive_operations": (
        "strategy",
        "operations",
        "enterprise",
        "initiatives",
        "business operations",
    ),
    "entertainment_marketing": (
        "marketing",
        "campaign",
        "audience",
        "brand",
        "creative",
    ),
    "music_industry": (
        "artist",
        "label",
        "music",
        "touring",
        "fan engagement",
    ),
    "product_ai": (
        "product",
        "ai",
        "automation",
        "systems",
        "platform",
        "workflow",
    ),
}

PathInput = Union[str, Path]

MATCH_PERSISTENCE_FIELDS = (
    "match_score",
    "match_tier",
    "match_summary",
    "match_strengths",
    "match_gaps",
    "recommended_action",
    "confidence",
)

FUNCTIONAL_SIGNAL_GROUPS = (
    ("ad/media operations", ("ad operations", "media operations", "trafficking", "media execution")),
    ("programmatic", ("programmatic", "ad tech", "adtech", "dsp", "ad server")),
    ("campaign operations", ("campaign operations", "marketing operations", "campaign management", "campaign execution")),
    ("marketing technology and measurement", ("marketing technology", "martech", "measurement", "vendor operations", "vendor management")),
    ("workflow and process automation", ("workflow", "automation", "process improvement", "operational excellence", "scalable process")),
    ("strategic operations", ("strategic operations", "business operations", "operating model", "transformation", "operational strategy", "strategy and operations")),
)

TARGET_INDUSTRY_SIGNALS = (
    "music",
    "entertainment",
    "streaming",
    "media",
    "creator economy",
    "creators",
    "advertising technology",
    "marketing technology",
    "martech",
    "brand marketing",
    "creative technology",
)

OBVIOUS_NON_FIT_SIGNALS = (
    "active medical license",
    "registered nurse",
    "licensed clinical",
    "admitted to the bar",
    "active bar membership",
    "certified public accountant required",
    "security clearance required",
    "software engineering degree required",
)

MINIMUM_MEANINGFUL_DESCRIPTION_LENGTH = 80
SCORING_ENGINE_VERSION = "astra-v2"
SCORING_INPUT_VERSION = "posting-body-v1"
EVIDENCE_NOISE = {"not", "people", "them", "they", "who", "what", "how", "one", "real", "more", "than"}


def incomplete_match_report(job_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a safe no-score gate when required import fields are incomplete."""
    company = str(job_data.get("company") or "").strip()
    title = str(job_data.get("job_title") or job_data.get("role") or "").strip()
    description = str(
        job_data.get("job_description") or job_data.get("description") or ""
    ).strip()
    missing = []
    if not company:
        missing.append("company")
    if not title:
        missing.append("role title")
    if len(description) < MINIMUM_MEANINGFUL_DESCRIPTION_LENGTH:
        missing.append("job description")
    if not missing:
        return None
    return {
        "job_title": title or None,
        "company": company or None,
        "match_score": None,
        "match_band": "Not scored",
        "match_tier": "Not scored",
        "match_summary": "Import is incomplete, so Career Catalyst has not scored this role.",
        "match_strengths": [],
        "match_gaps": ["Missing " + ", ".join(missing) + "."],
        "recommended_action": "Complete Import / Paste Job Description",
        "next_action": "Paste the job description and re-score before generating package.",
        "confidence": "Low",
        "top_matching_skills": [],
        "top_matching_projects": [],
        "top_matching_experience": [],
        "missing_keywords": [],
        "recommended_resume_profile": None,
        "tailoring_notes": [],
        "incomplete_import": True,
        "missing_required_fields": missing,
    }


def _flatten_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings = []
        for nested in value.values():
            strings.extend(_flatten_strings(nested))
        return strings
    if isinstance(value, list):
        strings = []
        for nested in value:
            strings.extend(_flatten_strings(nested))
        return strings
    return [str(value)]


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stem_token(token: str) -> str:
    if token == "strategic":
        return "strategy"
    if token in {"operational", "operations"}:
        return "operation"
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _terms(text: str) -> List[str]:
    normalized = _normalize_text(text)
    return [
        _stem_token(token)
        for token in normalized.split()
        if token and token not in GENERIC_TERMS and len(token) > 2
    ]


def _term_set(text: str) -> Set[str]:
    return set(_terms(text))


def _keyword_matches_text(keyword: str, text: str, allow_partial: bool = False) -> bool:
    normalized_keyword = _normalize_text(keyword)
    normalized_text = _normalize_text(text)

    if not normalized_keyword:
        return False
    if normalized_keyword in normalized_text:
        return True

    keyword_terms = _terms(keyword)
    if not keyword_terms:
        return False

    text_terms = _term_set(text)
    matches = sum(1 for term in keyword_terms if term in text_terms)
    if allow_partial:
        required_matches = max(1, len(keyword_terms) - 1)
    elif len(keyword_terms) <= 2:
        required_matches = len(keyword_terms)
    else:
        required_matches = len(keyword_terms) - 1
    return matches >= required_matches


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _job_terms(parsed_job: Dict[str, Any]) -> List[str]:
    values = []
    values.extend(parsed_job.get("keywords", []))
    values.extend(_flatten_strings(parsed_job.get("responsibilities", [])))
    values.extend(_flatten_strings(parsed_job.get("qualifications", [])))
    values.extend(_flatten_strings(parsed_job.get("preferred_qualifications", [])))
    return _dedupe([value for value in values if isinstance(value, str)])


def _important_keywords(parsed_job: Dict[str, Any]) -> List[str]:
    keywords = parsed_job.get("keywords", [])
    return [keyword for keyword in keywords if keyword and _terms(str(keyword)) and str(keyword).lower() not in EVIDENCE_NOISE]


def _skills_from_data(career_data: Dict[str, Any]) -> List[str]:
    skill_groups = career_data["data"]["skills"].get("skill_groups", {})
    return _dedupe(_flatten_strings(skill_groups))


def _evidence_text(projects: Optional[List[Dict[str, Any]]] = None) -> str:
    return "\n".join(_flatten_strings(projects or []))

def _candidate_text(career_data: Dict[str, Any], associated_evidence_projects: Optional[List[Dict[str, Any]]] = None) -> str:
    sections = [
        career_data["data"].get("skills", {}),
        career_data["data"].get("achievements", {}),
        career_data["data"].get("positions", {}),
        career_data["data"].get("projects", {}),
        career_data["data"].get("personal_brand", {}),
        career_data["config"].get("role_profiles", {}),
        associated_evidence_projects or [],
    ]
    return "\n".join(_flatten_strings(sections))


def _matched_keywords_for_text(keywords: Sequence[str], text: str, allow_partial: bool = False) -> List[str]:
    return [keyword for keyword in keywords if _keyword_matches_text(str(keyword), text, allow_partial)]


def _score_from_count(matched_count: int, target_count: int) -> float:
    if target_count <= 0:
        return 0.0
    return min(100.0, (matched_count / float(target_count)) * 100.0)


def _top_matching_skills(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> List[str]:
    job_text = "\n".join(_job_terms(parsed_job))
    matches = []
    for skill in _skills_from_data(career_data):
        if _keyword_matches_text(skill, job_text, allow_partial=True):
            matches.append(skill)
            continue

        skill_terms = set(_terms(skill))
        job_terms = _term_set(job_text)
        if skill_terms and len(skill_terms.intersection(job_terms)) >= max(1, len(skill_terms) - 1):
            matches.append(skill)

    return matches[:10]


def _top_matching_projects(career_data: Dict[str, Any], keywords: Sequence[str]) -> List[Dict[str, Any]]:
    projects = career_data["data"]["projects"].get("projects", [])
    matches = []

    for project in projects:
        text = "\n".join(_flatten_strings(project))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if not matched_keywords:
            continue
        matches.append(
            {
                "name": project.get("name", "Unnamed project"),
                "matched_keywords": matched_keywords[:5],
            }
        )

    return sorted(matches, key=lambda item: len(item["matched_keywords"]), reverse=True)[:3]


def _top_matching_experience(career_data: Dict[str, Any], keywords: Sequence[str]) -> List[Dict[str, Any]]:
    experience_items = []

    for achievement in career_data["data"]["achievements"].get("achievements", []):
        text = "\n".join(_flatten_strings(achievement))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if matched_keywords:
            experience_items.append(
                {
                    "source": "achievement",
                    "title": achievement.get("theme", achievement.get("id", "Achievement")),
                    "matched_keywords": matched_keywords[:5],
                }
            )

    for position in career_data["data"]["positions"].get("positions", []):
        text = "\n".join(_flatten_strings(position))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if matched_keywords:
            experience_items.append(
                {
                    "source": "position",
                    "title": position.get("company", "Position"),
                    "matched_keywords": matched_keywords[:5],
                }
            )

    return sorted(experience_items, key=lambda item: len(item["matched_keywords"]), reverse=True)[:5]


def _target_company_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    company = parsed_job.get("company")
    if not company:
        return 0.0

    for target_company in career_data["config"]["target_companies"].get("target_companies", []):
        if _normalize_text(target_company.get("name", "")) == _normalize_text(str(company)):
            return 40.0
    return 0.0


def _target_role_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    title = parsed_job.get("job_title") or ""
    title_terms = _term_set(str(title))
    if not title_terms:
        return 0.0

    best_score = 0.0
    for role_profile in career_data["config"]["role_profiles"].get("role_profiles", []):
        role_text = "\n".join(_flatten_strings(role_profile))
        role_terms = _term_set(role_text)
        if not role_terms:
            continue
        overlap = len(title_terms.intersection(role_terms))
        best_score = max(best_score, min(35.0, overlap / float(len(title_terms)) * 35.0))

    return best_score


def _industry_alignment_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    candidate_industries = career_data["data"]["personal_brand"].get("target_industries", [])
    target_company_industries = []
    company = parsed_job.get("company")

    for target_company in career_data["config"]["target_companies"].get("target_companies", []):
        if company and _normalize_text(target_company.get("name", "")) == _normalize_text(str(company)):
            target_company_industries.extend(target_company.get("industries", []))

    candidate_terms = _term_set(" ".join(_flatten_strings(candidate_industries)))
    job_terms = _term_set(" ".join(_job_terms(parsed_job) + _flatten_strings(target_company_industries)))
    if not candidate_terms:
        return 0.0

    overlap = len(candidate_terms.intersection(job_terms))
    return min(25.0, overlap / float(max(1, min(len(candidate_terms), 4))) * 25.0)


def _alignment_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    return min(
        100.0,
        _target_company_score(career_data, parsed_job)
        + _target_role_score(career_data, parsed_job)
        + _industry_alignment_score(career_data, parsed_job),
    )


def _match_band(score: float) -> str:
    if score >= 90:
        return "Excellent fit"
    if score >= 75:
        return "Strong fit"
    if score >= 60:
        return "Possible fit"
    if score >= 40:
        return "Weak fit"
    return "Poor fit"


def _recommended_resume_profile(parsed_job: Dict[str, Any]) -> str:
    text = " ".join(
        _flatten_strings(
            [
                parsed_job.get("job_title"),
                parsed_job.get("keywords", []),
                parsed_job.get("responsibilities", []),
                parsed_job.get("qualifications", []),
            ]
        )
    )

    best_profile = "executive_operations"
    best_count = -1
    for profile, keywords in RESUME_PROFILE_KEYWORDS.items():
        count = sum(1 for keyword in keywords if _keyword_matches_text(keyword, text, allow_partial=True))
        if count > best_count:
            best_profile = profile
            best_count = count

    return best_profile


def _missing_keywords(keywords: Sequence[str], candidate_text: str) -> List[str]:
    missing = []
    for keyword in keywords:
        if not _keyword_matches_text(str(keyword), candidate_text):
            missing.append(str(keyword))
    return missing[:8]


def _tailoring_notes(
    report: Dict[str, Any],
    top_skills: Sequence[str],
    top_projects: Sequence[Dict[str, Any]],
    top_experience: Sequence[Dict[str, Any]],
) -> List[str]:
    notes = []

    if top_skills:
        notes.append("Emphasize " + ", ".join(top_skills[:3]) + " as the opening skills cluster.")

    if report["missing_keywords"]:
        notes.append("Add or validate language for " + ", ".join(report["missing_keywords"][:3]) + " where it is accurate.")

    if top_projects:
        notes.append("Elevate " + str(top_projects[0]["name"]) + " as the strongest project proof point.")

    if top_experience:
        notes.append("Lead experience bullets with " + str(top_experience[0]["title"]) + " because it carries the strongest overlap.")

    if report["match_score"] >= 75:
        notes.append("This role is worth applying to based on the current structured data match.")
    else:
        notes.append("Apply selectively unless the missing keywords can be supported with accurate examples.")

    return notes[:6]


def persisted_match_fields(report: Dict[str, Any]) -> Dict[str, Any]:
    """Return a complete, tracker-valid match snapshot or no match fields.

    Scoring is allowed to produce an incomplete import/no-score report for
    previews.  That transient state is not a tracker state: returning an empty
    mapping lets the caller persist an unrelated mutation (such as Evidence
    selection) while preserving the previously saved canonical match fields.
    A report is persisted only when every field required by the strict tracker
    validator is present and valid, so every scoring write path shares one
    persistence boundary.
    """
    if not isinstance(report, dict) or report.get("incomplete_import"):
        return {}

    score = report.get("match_score")
    tier = report.get("match_tier")
    summary = report.get("match_summary")
    strengths = report.get("match_strengths")
    gaps = report.get("match_gaps")
    action = report.get("recommended_action")
    confidence = report.get("confidence")
    if (
        isinstance(score, bool)
        or not isinstance(score, int)
        or not 0 <= score <= 100
        or tier not in VALID_MATCH_TIERS
        or not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(strengths, list)
        or not 3 <= len(strengths) <= 5
        or not all(isinstance(value, str) and value.strip() for value in strengths)
        or not isinstance(gaps, list)
        or not 1 <= len(gaps) <= 5
        or not all(isinstance(value, str) and value.strip() for value in gaps)
        or action not in VALID_MATCH_ACTIONS
        or confidence not in VALID_MATCH_CONFIDENCE
    ):
        return {}

    fields = {field: report[field] for field in MATCH_PERSISTENCE_FIELDS}
    if isinstance(report.get("evaluation_snapshot"), dict):
        fields["evaluation_snapshot"] = dict(report["evaluation_snapshot"])
    return fields


def _empty_career_data() -> Dict[str, Any]:
    """Allow isolated intake fixtures to score safely without a full profile tree."""
    return {
        "data": {
            "skills": {"skill_groups": {}},
            "achievements": {"achievements": []},
            "positions": {"positions": []},
            "projects": {"projects": []},
            "personal_brand": {"target_industries": []},
        },
        "config": {
            "role_profiles": {"role_profiles": []},
            "target_companies": {"target_companies": []},
        },
    }


def _signal_groups(text: str) -> List[str]:
    lowered = text.lower()
    return [
        label
        for label, signals in FUNCTIONAL_SIGNAL_GROUPS
        if any(signal in lowered for signal in signals)
    ]


def _role_diagnostic_signals(
    parsed_job: Dict[str, Any],
    role_intelligence: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Return candidate-facing diagnostics from the effective role profile.

    The numeric score continues to use the canonical posting signals.  These
    labels explain that score using the same effective role family shown in the
    Tailoring Plan, so a re-parsed role cannot retain stale MarTech or generic
    skill wording in its explanation.
    """
    intelligence = role_intelligence or {}
    family = str(
        intelligence.get("role_family")
        or intelligence.get("generation_role_family")
        or ""
    ).strip().lower()
    label = str(intelligence.get("role_family_label") or "").strip().lower()
    if family == "experiential_live_event_production" or "experiential production" in label:
        return [
            "experiential production",
            "live-event execution",
            "production management",
            "budget and timeline management",
            "vendor and fabrication coordination",
            "venue and logistics coordination",
            "onsite execution",
        ]
    if family == "paid_media" or "paid media" in label:
        return [
            "paid media execution",
            "campaign setup and optimization",
            "measurement and tracking",
            "release-driven campaign timing",
        ]
    if family == "music_partnerships_label_relations" or "label relations" in label:
        return [
            "media operations",
            "entertainment partnerships",
            "partner coordination",
            "workflow governance",
        ]
    if family == "strategy_gtm_operations" or "strategy" in label and "operations" in label:
        return [
            "strategy and operations",
            "planning and resource allocation",
            "workflow governance",
            "cross-functional execution",
        ]
    return []


def _functional_fit(text: str) -> Tuple[int, List[str]]:
    matched = _signal_groups(text)
    if not matched:
        return 20, matched
    return min(100, 30 + (25 * len(matched))), matched


def _seniority_fit(title: Any) -> Tuple[int, str, bool]:
    lowered = str(title or "").lower()
    # Match explicit title tokens even when punctuation follows the token,
    # e.g. "VP, Campaign Management".
    if any(
        re.search(rf"(?<!\w){re.escape(signal.strip())}(?!\w)", lowered)
        for signal in ("chief", "vice president", "vp", "head of", "group director", "director")
    ):
        return 100, "The seniority is aligned with Trisha's director/head-of target level.", False
    if any(signal in lowered for signal in ("senior manager", "sr. manager", "sr manager", "principal", "lead")):
        return 90, "The seniority is aligned with Trisha's senior manager/lead target range.", False
    if "manager" in lowered or "senior" in lowered:
        return 65, "The role has meaningful ownership, though its level should be verified.", False
    if any(signal in lowered for signal in ("coordinator", "assistant", "junior", "entry level", "associate")):
        return 20, "", True
    return 55, "The role level is not explicit enough to confirm seniority fit.", False


def _industry_fit(text: str, company: Any = "") -> Tuple[int, Optional[str], bool]:
    lowered = text.lower()
    matches = [signal for signal in TARGET_INDUSTRY_SIGNALS if signal in lowered]
    company_lowered = str(company or "").lower()
    pure_agency = "agency" in company_lowered and not any(
        signal in lowered for signal in ("client-side", "in-house", "brand role", "brand team")
    )
    if matches:
        score = min(100, 75 + (8 * min(len(matches), 4)))
        if pure_agency:
            score = min(score, 60)
        return score, matches[0], pure_agency
    if pure_agency:
        return 35, None, True
    return 55, None, False


def _salary_amounts(salary_value: Any, raw_text: str) -> List[int]:
    compensation = normalize_compensation(
        salary_value if salary_value else raw_text,
        source="saved" if salary_value else "description",
    )
    if compensation.get("period") == "hour":
        annualized = [
            float(value) * 2080
            for value in (compensation.get("minimum"), compensation.get("maximum"))
            if value is not None
        ]
        return sorted({int(value) for value in annualized})
    return sorted(
        {
            int(value)
            for value in (compensation.get("minimum"), compensation.get("maximum"))
            if value is not None
        }
    )


def _salary_fit(
    salary_value: Any, raw_text: str
) -> Tuple[Optional[int], str, Optional[str], str]:
    normalized = normalize_compensation(
        salary_value if salary_value else raw_text,
        source="saved" if salary_value else "description",
    )
    state = str(normalized.get("disclosure_state") or "unknown_unverified")
    amounts = _salary_amounts(normalized, raw_text)
    if not amounts:
        if state == "not_listed":
            return (
                None,
                "Compensation not listed — verify before recruiter screen.",
                "Compensation was not listed; verify the range before the recruiter screen.",
                state,
            )
        return (
            None,
            "Compensation unknown — verify posting or recruiter details.",
            "Compensation is unknown; verify the posting or recruiter details.",
            "unknown_unverified",
        )
    minimum, maximum = min(amounts), max(amounts)
    display = str(normalized.get("display") or salary_value).strip()
    if minimum >= 150000:
        return 100, display, None, "provided"
    if maximum >= 150000:
        return 90, display, None, "provided"
    if minimum >= 120000:
        return 78, display, None, "provided"
    if maximum >= 120000:
        return 68, display, "The lower end of the range is below Trisha's $120k caution threshold.", "provided"
    if maximum >= 85000:
        return (
            45,
            display,
            "Compensation is below the $120k caution threshold; pursue only if the role is a strategic doorway.",
            "provided",
        )
    return 25, display, "Compensation is materially below Trisha's target range.", "provided"


def _work_arrangement(parsed_job: Dict[str, Any]) -> Tuple[int, str, Optional[str]]:
    raw_text = str(parsed_job.get("raw_text") or "")
    labeled = re.search(
        r"^\s*Work arrangement\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    arrangement = labeled.group(1).strip() if labeled else ""
    explicit = str(parsed_job.get("work_arrangement") or arrangement or "").strip()
    # Once the posting provides a labeled arrangement, unrelated mentions of
    # remote collaboration must not award remote-role credit.
    combined = (explicit or f"{parsed_job.get('location') or ''} {raw_text}").lower()
    heavy_onsite = bool(
        re.search(r"(?:minimum of\s+)?[4-5]\s+days?\s+per week\s+in (?:the )?office", combined)
        or "#li-onsite" in combined
    )
    if heavy_onsite:
        return 25, explicit or "Heavy on-site", "The heavy on-site requirement is a practical constraint, especially at lower pay."
    if "remote" in combined:
        return 100, explicit or "Remote", None
    if "hybrid" in combined:
        return 88, explicit or "Hybrid", None
    if any(signal in combined for signal in ("on-site", "onsite", "in office", "in-office")):
        return 45, explicit or "On-site", "The on-site requirement should be weighed against commute and compensation."
    if "flexible" in combined:
        return 82, explicit or "Flexible", None
    return 55, explicit or "Not specified", "Work arrangement is not specified."


def _confidence(
    parsed_job: Dict[str, Any],
    compensation_state: str,
    work_label: str,
    freshness: Dict[str, Any],
) -> str:
    missing = sum(
        (
            not bool(parsed_job.get("job_title")),
            not bool(parsed_job.get("company")),
            not bool(parsed_job.get("location")),
            compensation_state != "provided",
            work_label == "Not specified",
            freshness.get("age_days") is None,
        )
    )
    if missing <= 1:
        confidence = "High"
    elif missing <= 3:
        confidence = "Medium"
    else:
        confidence = "Low"
    if compensation_state != "provided" and confidence == "High":
        return "Medium"
    return confidence


def _match_tier(score: int) -> str:
    if score >= 82:
        return "Strong Match"
    if score >= 68:
        return "Good Match"
    if score >= 55:
        return "Stretch Match"
    if score >= 35:
        return "Weak Match"
    return "Pass"


def _decision_match_report(
    parsed_job: Dict[str, Any],
    legacy_report: Dict[str, Any],
    role_intelligence: Optional[Dict[str, Any]] = None,
    evidence_bonus: int = 0,
) -> Dict[str, Any]:
    raw_text = str(parsed_job.get("raw_text") or "")
    title = str(parsed_job.get("job_title") or "")
    combined = f"{title}\n{parsed_job.get('company') or ''}\n{raw_text}"
    functional_score, functional_matches = _functional_fit(combined)
    seniority_score, seniority_strength, junior_role = _seniority_fit(title)
    industry_score, industry_signal, pure_agency = _industry_fit(
        combined, parsed_job.get("company")
    )
    salary_score, salary_display, salary_gap, compensation_state = _salary_fit(
        parsed_job.get("compensation") or parsed_job.get("salary_range"), raw_text
    )
    work_score, work_label, work_gap = _work_arrangement(parsed_job)
    freshness = detect_job_freshness(raw_text)
    non_fit_signals = [signal for signal in OBVIOUS_NON_FIT_SIGNALS if signal in combined.lower()]
    diagnostic_signals = _role_diagnostic_signals(parsed_job, role_intelligence)

    weighted_score = (
        (legacy_report["match_score"] * 0.30)
        + (functional_score * 0.25)
        + (seniority_score * 0.15)
        + (industry_score * 0.12)
        + ((salary_score or 0) * 0.08)
        + (work_score * 0.05)
        + (int(freshness["score"]) * 0.05)
    )
    if salary_score is None:
        weighted_score /= 0.92
    score = round(weighted_score - (15 if non_fit_signals else 0)) + int(evidence_bonus)
    if freshness.get("is_closed"):
        score = min(score, 25)
    score = int(max(0, min(100, score)))
    tier = "Pass" if freshness.get("is_closed") else _match_tier(score)

    strengths: List[str] = []
    if diagnostic_signals:
        strengths.append("Functional alignment includes " + ", ".join(diagnostic_signals[:3]) + ".")
    elif functional_matches:
        strengths.append("Functional alignment includes " + ", ".join(functional_matches[:3]) + ".")
    if seniority_strength:
        strengths.append(seniority_strength)
    if industry_signal and not pure_agency:
        strengths.append(f"The {industry_signal} context is adjacent to Trisha's target industries.")
    if salary_score is not None and salary_score >= 78:
        strengths.append("The disclosed compensation is aligned with or near Trisha's target.")
    if work_score >= 82:
        strengths.append(f"The {work_label.lower()} arrangement supports practical fit.")
    if diagnostic_signals:
        strengths.append("Matched role signals include " + ", ".join(diagnostic_signals[:3]) + ".")
    elif legacy_report.get("top_matching_skills"):
        strengths.append(
            "Career evidence overlaps in "
            + ", ".join(str(value) for value in legacy_report["top_matching_skills"][:3])
            + "."
        )
    fallback_strengths = (
        "The role has enough detail for a pre-package fit review.",
        "The role title and employer are clearly identified.",
        "The listing can be evaluated before spending package-generation time.",
    )
    for strength in fallback_strengths:
        if len(strengths) >= 3:
            break
        strengths.append(strength)

    gaps: List[str] = []
    if salary_gap:
        gaps.append(salary_gap)
    if work_gap:
        gaps.append(work_gap)
    if freshness.get("is_closed"):
        gaps.append("The posting appears closed, so no package should be generated unless its status is verified.")
    elif freshness.get("age_days") is None:
        gaps.append("Posting age is unknown; verify that the role is still active.")
    elif freshness.get("category") in {"Aging", "Stale"}:
        gaps.append(f"The posting is {freshness['category'].lower()} at {freshness['age_days']} days old.")
    if junior_role:
        gaps.append("The role is below Trisha's target seniority.")
    if pure_agency:
        gaps.append("This appears to be an agency role; confirm that the scope is strategic and client-side adjacent.")
    if non_fit_signals:
        gaps.append(f"The listing includes a likely hard non-fit requirement: {non_fit_signals[0]}.")
    if not functional_matches:
        gaps.append("The listing shows limited alignment with Trisha's core operations background.")
    title = str(parsed_job.get("job_title") or "").lower()
    if "label relations" in title:
        gaps.append(
            "Direct label-relations and music-partnership ownership should be validated; "
            "adjacent media and partner-management experience is not the same as label-side experience."
        )
    if "sales strategy" in title and "operations" in title:
        gaps.append(
            "Direct sales-operations depth in territory planning, pipeline governance, and forecasting should be validated."
        )
    if not gaps:
        gaps.append("Confirm the reporting line and decision authority before generating the package.")

    if freshness.get("is_closed"):
        action = "Pass"
    elif tier in {"Strong Match", "Good Match"}:
        action = "Generate Package"
    elif tier == "Stretch Match":
        action = "Review First"
    elif tier == "Weak Match" and industry_score >= 75 and functional_score >= 55:
        action = "Review First"
    else:
        action = "Pass"
    if freshness.get("is_stale") and action == "Generate Package":
        action = "Review First"

    lead = {
        "Strong Match": "Strong alignment across Trisha's core experience, target level, and practical priorities.",
        "Good Match": "Good overall alignment, with a few cautions to weigh before investing further.",
        "Stretch Match": "There is credible alignment, but the tradeoffs deserve review before package generation.",
        "Weak Match": "The role has some overlap but falls short on important fit factors.",
        "Pass": "The current listing is not a sensible package-generation priority.",
    }[tier]
    if salary_score is not None and salary_score <= 45 and industry_score >= 75 and tier in {"Good Match", "Stretch Match"}:
        lead = "This could be a strategic doorway into a target industry, but the compensation gap is material."

    legacy_report.update(
        {
            "salary_range": salary_display,
            "compensation_disclosure_state": compensation_state,
            "salary_verification_action": (
                "Verify compensation before recruiter screen."
                if compensation_state != "provided"
                else ""
            ),
            "match_score": score,
            "match_band": _match_band(score),
            "match_tier": tier,
            "match_summary": lead,
            "match_strengths": _dedupe(strengths)[:5],
            "match_gaps": _dedupe(gaps)[:5],
            "recommended_action": action,
            "confidence": _confidence(parsed_job, compensation_state, work_label, freshness),
            "work_arrangement": work_label,
            "matched_signals": diagnostic_signals or functional_matches,
        }
    )
    return legacy_report


def _score_parsed_job(
    parsed_job: Dict[str, Any],
    root: Path,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intelligence: Optional[Dict[str, Any]] = None,
    career_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if career_data is None:
        try:
            career_data = load_resume_foundation(root)
        except DataLoadError:
            career_data = _empty_career_data()
    keywords = _important_keywords(parsed_job)
    associated_evidence_projects = associated_evidence_projects or []
    candidate_text = _candidate_text(career_data, associated_evidence_projects)

    top_skills = _top_matching_skills(career_data, parsed_job)
    top_projects = _top_matching_projects(career_data, keywords)
    top_experience = _top_matching_experience(career_data, keywords)
    evidence_text = _evidence_text(associated_evidence_projects)
    evidence_matches = _matched_keywords_for_text(keywords, evidence_text)
    # Selected Evidence affects the score only through the posting requirements
    # it supports, never through incidental keyword overlap.  Coverage can only
    # grow as Evidence is added, so the adjusted score never drops below base.
    coverage = match_evidence_to_requirements(parsed_job, associated_evidence_projects)
    evidence_bonus = requirement_coverage_bonus(coverage) if associated_evidence_projects else 0
    evidence_match_details = list(coverage["matched_labels"])
    missing_keywords = _missing_keywords(keywords, candidate_text)

    skill_score = _score_from_count(len(top_skills), 6)
    experience_matched_keywords = set()
    for item in top_experience:
        experience_matched_keywords.update(item["matched_keywords"])
    experience_score = _score_from_count(len(experience_matched_keywords), 8)
    project_score = _score_from_count(len(top_projects), 2)
    alignment_score = _alignment_score(career_data, parsed_job)

    match_score = round(
        (skill_score * 0.35)
        + (experience_score * 0.30)
        + (project_score * 0.20)
        + (alignment_score * 0.15)
    )

    report = {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "location": parsed_job.get("location"),
        "salary_range": parsed_job.get("salary_range"),
        "match_score": int(max(0, min(100, match_score))),
        "match_band": _match_band(match_score),
        "top_matching_skills": top_skills,
        "top_matching_projects": top_projects,
        "top_matching_experience": top_experience,
        "associated_evidence_count": len(associated_evidence_projects),
        "associated_evidence_project_titles": [str(p.get("title")) for p in associated_evidence_projects if p.get("title")],
        "associated_evidence_matches": evidence_matches[:8],
        "associated_evidence_match_details": evidence_match_details[:8],
        "requirement_coverage": coverage,
        "evidence_requirement_bonus": evidence_bonus,
        "missing_keywords": missing_keywords,
        "recommended_resume_profile": _recommended_resume_profile(parsed_job),
        "tailoring_notes": [],
    }
    report = _decision_match_report(parsed_job, report, role_intelligence, evidence_bonus)
    if associated_evidence_projects and not coverage["covered_count"]:
        # A Strong/High verdict must not sit next to "no Evidence-supported
        # matches": say plainly that the selected Evidence supports nothing.
        if report.get("confidence") == "High":
            report["confidence"] = "Medium"
        report["match_gaps"] = _dedupe([
            "Selected Evidence does not support any parsed posting requirement; choose Evidence closer to the role.",
            *report.get("match_gaps", []),
        ])[:5]
    report["tailoring_notes"] = _tailoring_notes(
        report, top_skills, top_projects, top_experience
    )
    return report


def _evaluation_fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_posting(job: Dict[str, Any]) -> Dict[str, Any]:
    """Separate substantive posting text from storage/UI metadata exactly once."""
    text = _analysis_text(str(job.get("job_description") or job.get("raw_text") or ""))
    heading = re.search(r"^##\s+Job Description\s*$", text, re.I | re.M)
    if heading:
        body = text[heading.end():].strip()
    else:
        lines = text.splitlines()
        # Only remove the leading serialization envelope, never body labels.
        while lines and (not lines[0].strip() or re.match(
            r"^(?:# |Company:|Location:|Work arrangement:|Salary range:|Posting date:|"
            r"Tracker ID:|Official URL:|Source type:|Verification status:)", lines[0], re.I
        )):
            lines.pop(0)
        body = "\n".join(lines).strip()
    metadata = extract_metadata(text)
    parsed = {**metadata, **{k: v for k, v in job.items() if v not in (None, "")}}
    parsed["job_title"] = job.get("job_title") or job.get("role") or metadata.get("job_title")
    parsed["company"] = job.get("company") or metadata.get("company")
    parsed["job_description"] = body
    # Stable metadata is available for practical-fit scoring, but cannot enter
    # the keyword-frequency ranking or masquerade as a requirement.
    prefix = "\n".join(f"{label}: {parsed.get(key)}" for label, key in (
        ("Posting date", "posting_date"), ("Work arrangement", "work_arrangement"),
    ) if parsed.get(key))
    parsed["raw_text"] = (prefix + "\n\n" + body).strip()
    parsed["keywords"] = extract_keywords(body)
    parsed["responsibilities"] = extract_responsibilities(body)
    parsed["qualifications"] = extract_qualifications(body)
    parsed["preferred_qualifications"] = extract_preferred_qualifications(body)
    return parsed


def _score_with_snapshot(
    parsed_job: Dict[str, Any],
    root: Path,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intelligence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score one immutable posting/profile snapshot with Evidence separated."""
    parsed_job = normalized_posting(parsed_job)
    selected = list(associated_evidence_projects or [])
    try:
        career_data = load_resume_foundation(root)
    except DataLoadError:
        career_data = _empty_career_data()
    base = _score_parsed_job(parsed_job, root, [], role_intelligence, career_data)
    report = _score_parsed_job(parsed_job, root, selected, role_intelligence, career_data) if selected else dict(base)
    evidence_ids = sorted(
        str(item.get("id") or item.get("title") or "") for item in selected
    )
    posting_inputs = {
        key: parsed_job.get(key)
        for key in (
            "job_title", "company", "location", "work_arrangement", "salary_range",
            "posting_date", "raw_text", "responsibilities", "qualifications",
        )
    }
    base_score = int(base.get("match_score") or 0)
    final_score = int(report.get("match_score") or 0)
    report.update(
        {
            "base_match_report": dict(base),
            "base_match_score": base_score,
            "evidence_score_delta": final_score - base_score,
            "evaluation_snapshot": {
                "engine_version": SCORING_ENGINE_VERSION,
                "posting_fingerprint": _evaluation_fingerprint(posting_inputs),
                "profile_fingerprint": _evaluation_fingerprint(career_data),
                "evidence_fingerprint": _evaluation_fingerprint(selected),
                "input_version": SCORING_INPUT_VERSION,
                "evaluation_date": date.today().isoformat(),
                "base_score": base_score,
                "adjusted_score": final_score,
                "evidence_delta": final_score - base_score,
                "previous_evaluation_id": None,
                "evidence_ids": evidence_ids,
            },
        }
    )
    snapshot = report["evaluation_snapshot"]
    snapshot["evaluation_id"] = _evaluation_fingerprint(snapshot)
    return report


def score_job_data(
    job_data: Dict[str, Any],
    project_root: Optional[PathInput] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intelligence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score unsaved intake data so the UI can show the gate before generation."""
    incomplete = incomplete_match_report(job_data)
    if incomplete:
        return incomplete
    root = Path(project_root) if project_root is not None else Path.cwd()
    raw_text = str(job_data.get("job_description") or job_data.get("raw_text") or "")
    metadata_lines = "\n".join(
        line
        for line in (
            f"# {job_data.get('job_title') or job_data.get('role') or ''}",
            f"Company: {job_data.get('company') or ''}",
            f"Location: {job_data.get('location') or ''}",
            f"Work arrangement: {job_data.get('work_arrangement') or ''}",
            f"Salary range: {job_data.get('salary_range') or ''}",
            f"Posting date: {job_data.get('posting_date') or ''}",
        )
        if not line.endswith(": ") and line != "# "
    )
    canonical_text = f"{metadata_lines}\n\n{raw_text}".strip()
    parsed_job = {
        "raw_text": canonical_text,
        "job_title": job_data.get("job_title") or job_data.get("role"),
        "company": job_data.get("company"),
        "location": job_data.get("location"),
        "salary_range": job_data.get("salary_range"),
        "compensation": job_data.get("compensation") or normalize_compensation(
            job_data.get("salary_range") or raw_text,
            source="saved" if job_data.get("salary_range") else "description",
            disclosure_state=job_data.get("compensation_disclosure_state"),
        ),
        "posting_date": job_data.get("posting_date"),
        "work_arrangement": job_data.get("work_arrangement"),
        "job_description": raw_text,
        "keywords": extract_keywords(canonical_text),
        "responsibilities": extract_responsibilities(canonical_text),
        "qualifications": extract_qualifications(canonical_text),
        "preferred_qualifications": extract_preferred_qualifications(canonical_text),
    }
    return _score_with_snapshot(parsed_job, root, associated_evidence_projects, role_intelligence)


def score_job_match(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intelligence: Optional[Dict[str, Any]] = None,
    job_data_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the legacy tailoring report plus the Sprint 13 decision gate."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    parsed_job = parse_job_description(root / job_path)
    if job_data_override is not None:
        parsed_job.update({key: value for key, value in job_data_override.items() if value is not None})
        if "salary_range" in job_data_override and "compensation" not in job_data_override:
            parsed_job["compensation"] = normalize_compensation(
                job_data_override["salary_range"], source="saved",
                disclosure_state=job_data_override.get("compensation_disclosure_state"),
            )
    raw_text = str(parsed_job.get("job_description") or parsed_job.get("raw_text") or "")
    description_match = re.search(
        r"^##\s+Job Description\s*$\n(.*)", raw_text, flags=re.I | re.M | re.S
    )
    incomplete = incomplete_match_report(
        {
            **parsed_job,
            "job_description": (
                description_match.group(1).strip() if description_match else raw_text
            ),
        }
    )
    if incomplete:
        return incomplete
    return _score_with_snapshot(parsed_job, root, associated_evidence_projects, role_intelligence)
