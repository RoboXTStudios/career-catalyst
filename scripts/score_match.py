"""Score a parsed job description against Career Catalyst data."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

try:
    from .load_data import load_all_yaml
    from .parse_job import parse_job_description
except ImportError:
    from load_data import load_all_yaml
    from parse_job import parse_job_description


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
    return _dedupe([value for value in values if isinstance(value, str)])


def _important_keywords(parsed_job: Dict[str, Any]) -> List[str]:
    keywords = parsed_job.get("keywords", [])
    return [keyword for keyword in keywords if keyword and _terms(str(keyword))]


def _skills_from_data(career_data: Dict[str, Any]) -> List[str]:
    skill_groups = career_data["data"]["skills"].get("skill_groups", {})
    return _dedupe(_flatten_strings(skill_groups))


def _candidate_text(career_data: Dict[str, Any]) -> str:
    sections = [
        career_data["data"].get("skills", {}),
        career_data["data"].get("achievements", {}),
        career_data["data"].get("positions", {}),
        career_data["data"].get("projects", {}),
        career_data["data"].get("personal_brand", {}),
        career_data["config"].get("role_profiles", {}),
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


def score_job_match(job_path: PathInput, project_root: Optional[PathInput] = None) -> Dict[str, Any]:
    """Return a structured match report for a local job description."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    parsed_job = parse_job_description(root / job_path)
    career_data = load_all_yaml(root)
    keywords = _important_keywords(parsed_job)
    candidate_text = _candidate_text(career_data)

    top_skills = _top_matching_skills(career_data, parsed_job)
    top_projects = _top_matching_projects(career_data, keywords)
    top_experience = _top_matching_experience(career_data, keywords)
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
        "missing_keywords": missing_keywords,
        "recommended_resume_profile": _recommended_resume_profile(parsed_job),
        "tailoring_notes": [],
    }
    report["tailoring_notes"] = _tailoring_notes(report, top_skills, top_projects, top_experience)
    return report
