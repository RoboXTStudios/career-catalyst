"""Generate tailored Markdown resumes from structured Career Catalyst data."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

try:
    from .load_data import load_all_yaml
    from .parse_job import parse_job_description
    from .score_match import score_job_match
except ImportError:
    from load_data import load_all_yaml
    from parse_job import parse_job_description
    from score_match import score_job_match


VALID_RESUME_PROFILES = (
    "executive_operations",
    "entertainment_marketing",
    "music_industry",
    "product_ai",
)

PROFILE_PRIORITIES = {
    "executive_operations": (
        "business operations",
        "marketing operations",
        "operational strategy",
        "process excellence",
        "workflow governance",
        "cross-functional leadership",
        "ai workflow design",
        "change management",
        "stakeholder management",
    ),
    "entertainment_marketing": (
        "marketing operations",
        "campaign execution",
        "entertainment marketing",
        "creative operations",
        "measurement",
        "analytics",
        "brand",
    ),
    "music_industry": (
        "music",
        "fandom",
        "culture",
        "creative operations",
        "marketing",
        "storytelling",
        "partnership",
    ),
    "product_ai": (
        "campaignos",
        "ai workflow design",
        "operational automation",
        "product development",
        "workflow governance",
        "validation frameworks",
        "operational reporting",
    ),
}

PROJECT_RELEVANCE_TERMS = {
    "OMG23 Multiverse Newsletter": (
        "creative",
        "culture",
        "content",
        "storytelling",
        "editorial",
        "innovation",
        "emerging media",
    ),
    "Substack Writer": (
        "storytelling",
        "content",
        "creative",
        "music",
        "editorial",
        "writer",
        "publishing",
    ),
}

CONTACT_LINE = (
    "Los Angeles, CA | [tslynch@mac.com](mailto:tslynch@mac.com) | "
    "LinkedIn: linkedin.com/in/trishalynch"
)

PathInput = Union[str, Path]


class ResumeTailoringError(Exception):
    """Raised when a tailored resume cannot be generated."""


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


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(value)
    return deduped


def _score_text(text: str, keywords: Sequence[str], priorities: Sequence[str]) -> int:
    normalized = _normalize_text(text)
    score = 0
    for keyword in keywords:
        if _normalize_text(str(keyword)) in normalized:
            score += 3
    for priority in priorities:
        if _normalize_text(priority) in normalized:
            score += 4
    return score


def _is_near_duplicate(candidate: str, existing_values: Sequence[str]) -> bool:
    candidate_terms = set(_normalize_text(candidate).split())
    if not candidate_terms:
        return False

    for existing in existing_values:
        existing_terms = set(_normalize_text(existing).split())
        if not existing_terms:
            continue
        overlap = len(candidate_terms.intersection(existing_terms))
        if overlap / float(min(len(candidate_terms), len(existing_terms))) >= 0.70:
            return True

    return False


def _all_skills(career_data: Dict[str, Any]) -> List[str]:
    skill_groups = career_data["data"]["skills"].get("skill_groups", {})
    business_skills = _flatten_strings(
        {
            "business_and_operations": skill_groups.get("business_and_operations", []),
            "leadership_and_strategy": skill_groups.get("leadership_and_strategy", []),
            "ai_and_systems": skill_groups.get("ai_and_systems", []),
        }
    )
    return _dedupe(business_skills)


def _select_core_competencies(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    match_report: Dict[str, Any],
    resume_profile: str,
) -> List[str]:
    skills = _all_skills(career_data)
    job_keywords = [str(keyword) for keyword in parsed_job.get("keywords", [])]
    priorities = PROFILE_PRIORITIES[resume_profile]
    top_matching = match_report.get("top_matching_skills", [])

    ranked = []
    for index, skill in enumerate(skills):
        score = _score_text(skill, job_keywords, priorities)
        if skill in top_matching:
            score += 8
        ranked.append((score, -index, skill))

    selected = [skill for _score, _index, skill in sorted(ranked, reverse=True) if _score > 0]
    if len(selected) < 8:
        selected.extend(skills)
    return _dedupe(selected)[:12]


def _platform_categories(career_data: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    categories = career_data["data"]["platforms"].get("platform_categories", [])
    return [
        (str(category["name"]), [str(item) for item in category.get("items", [])])
        for category in categories
        if isinstance(category, dict) and category.get("name")
    ]


def _profile_summary(
    career_data: Dict[str, Any],
    match_report: Dict[str, Any],
    competencies: Sequence[str],
    resume_profile: str,
) -> str:
    personal_brand = career_data["data"]["personal_brand"]
    career_profile = personal_brand["career_profile"]
    profile_summary = career_profile.get("profile_summaries", {}).get(resume_profile)
    if profile_summary:
        return str(profile_summary)

    summary = str(career_profile["summary"])
    positioning_points = career_profile.get("positioning_points", [])
    return " ".join([summary] + [str(point) for point in positioning_points[:2]])


def _achievement_bullets(career_data: Dict[str, Any]) -> List[str]:
    bullets = []
    for achievement in career_data["data"]["achievements"].get("achievements", []):
        if achievement.get("id") == "campaignos_ai_operations":
            continue
        statement = achievement.get("statement")
        if statement:
            bullets.append(str(statement))
        for evidence in achievement.get("evidence", []):
            bullets.append(str(evidence))
    return bullets


def _select_experience_bullets(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    resume_profile: str,
) -> List[str]:
    positions = career_data["data"]["positions"].get("positions", [])
    omg_position = next(
        (position for position in positions if "OMG23" in position.get("company", "")),
        positions[0] if positions else {},
    )

    candidate_bullets = []
    candidate_bullets.extend(omg_position.get("highlights", []))
    candidate_bullets.extend(_achievement_bullets(career_data))

    sample_priorities = (
        "60+",
        "cross-functional",
        "operational execution",
        "disney+",
        "workflow",
        "governance",
        "technology",
        "analytics",
        "creative",
        "multimillion-dollar",
    )
    keywords = [str(keyword) for keyword in parsed_job.get("keywords", [])]
    priorities = PROFILE_PRIORITIES[resume_profile] + sample_priorities

    ranked = []
    for index, bullet in enumerate(_dedupe(candidate_bullets)):
        score = _score_text(bullet, keywords, priorities)
        ranked.append((score, -index, bullet))

    selected = []
    for _score, _index, bullet in sorted(ranked, reverse=True):
        normalized = _normalize_text(bullet)
        if any(normalized in _normalize_text(existing) or _normalize_text(existing) in normalized for existing in selected):
            continue
        if _is_near_duplicate(bullet, selected):
            continue
        selected.append(bullet)
        if len(selected) == 8:
            break
    return selected


def _campaignos_bullets(career_data: Dict[str, Any]) -> List[str]:
    projects = career_data["data"]["projects"].get("projects", [])
    achievements = career_data["data"]["achievements"].get("achievements", [])
    campaignos = next((project for project in projects if project.get("name") == "CampaignOS"), {})
    campaignos_achievement = next(
        (achievement for achievement in achievements if achievement.get("id") == "campaignos_ai_operations"),
        {},
    )

    bullets = []
    if campaignos_achievement.get("statement"):
        bullets.append(str(campaignos_achievement["statement"]))
    elif campaignos.get("summary"):
        bullets.append(str(campaignos["summary"]))

    bullets.extend(str(evidence) for evidence in campaignos_achievement.get("evidence", []))
    if len(bullets) < 3:
        bullets.extend(str(highlight) for highlight in campaignos.get("highlights", []))

    return _dedupe(bullets)[:3]


def _project_is_relevant(project_name: str, parsed_job: Dict[str, Any], resume_profile: str) -> bool:
    if project_name == "CampaignOS":
        return True

    text = " ".join(_flatten_strings(parsed_job.get("keywords", [])))
    project_terms = PROJECT_RELEVANCE_TERMS.get(project_name, ())
    normalized = _normalize_text(text)
    return any(_normalize_text(term) in normalized for term in project_terms)


def _selected_projects(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    resume_profile: str,
) -> List[Tuple[Dict[str, Any], List[str]]]:
    projects = career_data["data"]["projects"].get("projects", [])
    selected = []

    campaignos = next((project for project in projects if project.get("name") == "CampaignOS"), None)
    if campaignos:
        selected.append((campaignos, _campaignos_bullets(career_data)))

    for project in projects:
        name = project.get("name")
        if name == "CampaignOS" or not _project_is_relevant(str(name), parsed_job, resume_profile):
            continue
        bullets = [project.get("summary", "")]
        bullets.extend(project.get("highlights", [])[:3])
        selected.append((project, _dedupe([str(bullet) for bullet in bullets if bullet])))

    return selected


def _earlier_career(career_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    positions = career_data["data"]["positions"].get("positions", [])
    for position in positions:
        if "Intermedia" in position.get("company", ""):
            return position
    return None


def _professional_development(career_data: Dict[str, Any]) -> List[str]:
    certification_lines = []
    for certification in career_data["data"]["certifications"].get("certifications", []):
        areas = ", ".join(certification.get("areas", []))
        certification_lines.append(f"{certification.get('provider')}: {areas}")

    focus_areas = career_data["data"]["personal_brand"].get("current_focus", [])
    if focus_areas:
        certification_lines.append("Current focus: " + ", ".join(focus_areas))

    return certification_lines


def _company_slug(company: Optional[str]) -> str:
    if not company:
        return "sample"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_")
    return slug or "sample"


def _render_markdown(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    match_report: Dict[str, Any],
    resume_profile: str,
) -> str:
    personal_brand = career_data["data"]["personal_brand"]
    candidate = personal_brand["candidate"]
    competencies = _select_core_competencies(career_data, parsed_job, match_report, resume_profile)
    platforms = _platform_categories(career_data)
    positions = career_data["data"]["positions"].get("positions", [])
    omg_position = next(
        (position for position in positions if "OMG23" in position.get("company", "")),
        positions[0] if positions else {},
    )
    experience_bullets = _select_experience_bullets(career_data, parsed_job, resume_profile)
    selected_projects = _selected_projects(career_data, parsed_job, resume_profile)
    earlier_position = _earlier_career(career_data)
    development = _professional_development(career_data)

    lines = [
        f"# {candidate.get('name', 'Trisha Lynch')}",
        "",
        candidate.get("headline", ""),
        "",
        CONTACT_LINE,
        "",
        "## Profile",
        "",
        _profile_summary(career_data, match_report, competencies, resume_profile),
        "",
        "## Core Competencies",
        "",
    ]

    lines.extend(f"- {competency}" for competency in competencies)
    lines.extend(["", "## Platforms & Technologies", ""])

    for group_name, tools in platforms:
        if tools:
            lines.extend([f"### {group_name}", "", ", ".join(tools), ""])

    if omg_position:
        progression = " to ".join(omg_position.get("progression", []))
        lines.extend(
            [
                "## Professional Experience",
                "",
                f"### {omg_position.get('company')}",
                "",
                f"{omg_position.get('location')} | {omg_position.get('timeframe')}",
                "",
                progression,
                "",
            ]
        )
        lines.extend(f"- {bullet}" for bullet in experience_bullets)
        lines.append("")

    lines.extend(["## Selected Projects", ""])
    for project, bullets in selected_projects:
        lines.extend(
            [
                f"### {project.get('name')}",
                "",
                f"{project.get('role')} | {project.get('timeframe')}",
                "",
            ]
        )
        lines.extend(f"- {bullet}" for bullet in bullets)
        lines.append("")

    if earlier_position:
        progression = ", ".join(earlier_position.get("progression", []))
        lines.extend(
            [
                "## Earlier Career",
                "",
                f"### {earlier_position.get('company')}",
                "",
                f"{earlier_position.get('location')} | {earlier_position.get('timeframe')}",
                "",
                f"{progression}: {earlier_position.get('summary')}",
                "",
            ]
        )
        lines.extend(f"- {highlight}" for highlight in earlier_position.get("highlights", []))
        lines.append("")

    lines.extend(["## Professional Development", ""])
    lines.extend(f"- {line}" for line in development)
    lines.append("")

    return "\n".join(line for line in lines if line is not None)


def tailor_resume(
    resume_profile: str,
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate and save a tailored Markdown resume."""
    if resume_profile not in VALID_RESUME_PROFILES:
        valid = ", ".join(VALID_RESUME_PROFILES)
        raise ResumeTailoringError(f"Unknown resume profile '{resume_profile}'. Valid profiles: {valid}")

    root = Path(project_root) if project_root is not None else Path.cwd()
    career_data = load_all_yaml(root)
    parsed_job = parse_job_description(root / job_path)
    match_report = score_job_match(job_path, root)
    markdown = _render_markdown(career_data, parsed_job, match_report, resume_profile)

    export_dir = root / "exports" / "markdown"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / (
        f"Trisha_Lynch_{resume_profile}_{_company_slug(parsed_job.get('company'))}_Resume.md"
    )
    output_path.write_text(markdown, encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "resume_profile": resume_profile,
        "recommended_resume_profile": match_report.get("recommended_resume_profile"),
        "match_score": match_report.get("match_score"),
        "match_band": match_report.get("match_band"),
        "tailoring_notes": match_report.get("tailoring_notes", []),
        "output_path": str(output_path),
    }
