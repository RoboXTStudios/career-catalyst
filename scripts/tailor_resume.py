"""Generate tailored Markdown resumes from structured Career Catalyst data."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

try:
    from .career_claims import is_ai_transformation_role, validate_public_career_claims
    from .filename_utils import build_upload_filename
    from .resume_foundation import (
        CandidateLanguageError,
        load_resume_foundation,
        validate_candidate_language,
    )
    from .evidence_engine import evidence_generation_context, load_writing_voice_profile
    from .parse_job import parse_job_description
    from .package_context import validate_material_context
    from .role_context import is_google_youtube_role
    from .role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from .score_match import score_job_match
    from .text_cleanup import cleanup_repeated_words
except ImportError:
    from career_claims import is_ai_transformation_role, validate_public_career_claims
    from filename_utils import build_upload_filename
    from resume_foundation import (
        CandidateLanguageError,
        load_resume_foundation,
        validate_candidate_language,
    )
    from evidence_engine import evidence_generation_context, load_writing_voice_profile
    from parse_job import parse_job_description
    from package_context import validate_material_context
    from role_context import is_google_youtube_role
    from role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from score_match import score_job_match
    from text_cleanup import cleanup_repeated_words


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

GOOGLE_YOUTUBE_COMPETENCIES = (
    "YouTube Product Activation",
    "GTM Operations",
    "Large Advertiser Campaign Operations",
    "Brand Auction & Video Activation",
    "Seller Enablement",
    "Senior Stakeholder Alignment",
    "Product Feedback Loops",
    "Operational Excellence",
)

PROJECT_RELEVANCE_TERMS = {
    "Career Catalyst": (
        "product operations", "workflow", "ai", "automation", "requirements",
        "governance", "quality", "qa", "product thinking", "operational systems",
        "roadmap", "backlog", "iterate", "iteration",
    ),
    "RoboXT Studios": (
        "creative operations", "creative production", "content", "editorial",
        "photography", "publishing", "audience", "brand", "creator", "programming",
    ),
    "CampaignOS": (
        "campaign operations", "marketing technology", "martech", "measurement",
        "workflow", "governance", "automation", "quality assurance", "qa",
    ),
    "OMG23 Multiverse Newsletter": (
        "creative",
        "culture",
        "content",
        "storytelling",
        "editorial",
        "innovation",
        "emerging media",
    ),
}

PathInput = Union[str, Path]


class ResumeTailoringError(Exception):
    """Raised when a tailored resume cannot be generated."""


def _contact_line(personal_brand: Dict[str, Any]) -> str:
    candidate = personal_brand.get("candidate", {})
    location = candidate.get("location", "Los Angeles, CA")
    email = candidate.get("email", "tslynch@mac.com")
    linkedin_label = candidate.get("linkedin_label", "LinkedIn")
    linkedin_url = candidate.get(
        "linkedin_url",
        "[https://www.linkedin.com/in/trisha-lynch-3433417]"
        "(https://www.linkedin.com/in/trisha-lynch-3433417)",
    )
    return (
        f"{location} | [{email}](mailto:{email}) | "
        f"{linkedin_label}: {linkedin_url}"
    )


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
    if is_google_youtube_role(parsed_job):
        selected = list(GOOGLE_YOUTUBE_COMPETENCIES) + selected
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


def _selected_platform_categories(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    resume_profile: str,
) -> List[Tuple[str, List[str]]]:
    """Return a compact role-relevant tool set instead of the full foundation."""
    categories = _platform_categories(career_data)
    role_text = _normalize_text(
        " ".join(
            _flatten_strings(
                [
                    parsed_job.get("job_title"),
                    parsed_job.get("raw_text"),
                    parsed_job.get("keywords", []),
                    PROFILE_PRIORITIES.get(resume_profile, ()),
                ]
            )
        )
    )
    if is_ai_transformation_role(parsed_job):
        preferred = {
            "Business Productivity & Collaboration": (
                "Microsoft Teams", "Airtable", "Microsoft 365"
            ),
            "Operations & Program Management": (
                "Workflow Design", "Requirements Development", "Platform Governance",
                "Quality-Assurance Frameworks", "Training", "Adoption",
            ),
            "AI, Automation & Product Development": (
                "ChatGPT", "Codex", "AI Workflow Design", "Prompt and Schema Development",
                "Process Automation", "Product Prototyping",
            ),
        }
        return [
            (name, [item for item in items if item in preferred[name]][:6])
            for name, items in categories
            if name in preferred
        ]

    ranked: List[Tuple[int, int, str, List[str]]] = []
    for category_index, (name, items) in enumerate(categories):
        scored = []
        for item_index, item in enumerate(items):
            terms = _normalize_text(item).split()
            score = sum(2 for term in terms if len(term) > 2 and term in role_text)
            if score:
                scored.append((score, -item_index, item))
        selected = [item for _score, _index, item in sorted(scored, reverse=True)[:5]]
        if selected:
            ranked.append((sum(score for score, _index, _item in scored), -category_index, name, selected))
    if not ranked:
        fallbacks = {
            "Business Productivity & Collaboration": {"Microsoft 365", "Microsoft Teams", "Airtable"},
            "Operations & Program Management": {"Workflow Design", "Operating Models", "Process Documentation"},
        }
        return [
            (name, [item for item in items if item in fallbacks.get(name, set())])
            for name, items in categories
            if name in fallbacks
        ]
    return [(name, items) for _score, _index, name, items in sorted(ranked, reverse=True)[:3]]


def _profile_summary(
    career_data: Dict[str, Any],
    match_report: Dict[str, Any],
    competencies: Sequence[str],
    resume_profile: str,
    parsed_job: Dict[str, Any],
) -> str:
    personal_brand = career_data["data"]["personal_brand"]
    career_profile = personal_brand["career_profile"]
    profile_key = "google_youtube_operations" if is_google_youtube_role(parsed_job) else resume_profile
    profile_summary = career_profile.get("profile_summaries", {}).get(profile_key)
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


def _achievement_statement(career_data: Dict[str, Any], achievement_id: str) -> str:
    achievements = career_data["data"]["achievements"].get("achievements", [])
    return str(
        next(
            (
                item.get("statement")
                for item in achievements
                if item.get("id") == achievement_id
            ),
            "",
        )
        or ""
    )


def _foundation_evidence_project(
    career_data: Dict[str, Any], project_id: str
) -> Dict[str, Any]:
    projects = career_data["data"].get("evidence_projects", {}).get(
        "evidence_projects", []
    )
    return next((item for item in projects if item.get("id") == project_id), {})


def _ai_transformation_experience_bullets(
    career_data: Dict[str, Any], omg_position: Dict[str, Any]
) -> List[str]:
    airtable = _foundation_evidence_project(
        career_data, "operational_workflow_design_airtable_implementation"
    )
    teams = _foundation_evidence_project(
        career_data, "enterprise_collaboration_platform_adoption_stakeholder_enablement"
    )
    disney_plus = _achievement_statement(career_data, "disney_plus_launch_support")
    governance = _achievement_statement(career_data, "workflow_governance")
    leadership = _achievement_statement(career_data, "cross_functional_leadership")
    disney_task_force = next(
        (
            str(item)
            for item in omg_position.get("highlights", [])
            if "task force" in str(item).lower() and "Disney+" in str(item)
        ),
        disney_plus,
    )
    return _dedupe(
        [
            leadership,
            (
                "Coordinated an Airtable implementation as a shared source of truth, aligning "
                "workflows, naming conventions, permissions, QA, training, automations, and adoption."
                if airtable else ""
            ),
            (
                "Supported Microsoft Teams adoption through recurring office hours, troubleshooting, "
                "onboarding guidance, and a peer champion network."
                if teams else ""
            ),
            disney_task_force,
            governance,
        ]
    )[:6]


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
    if is_ai_transformation_role(parsed_job):
        return _ai_transformation_experience_bullets(career_data, omg_position)

    candidate_bullets = []
    candidate_bullets.extend(omg_position.get("highlights", []))
    candidate_bullets.extend(_achievement_bullets(career_data))

    sample_priorities = (
        "10 direct reports",
        "64-person organization",
        "cross-functional",
        "operational execution",
        "disney studios theatrical",
        "disney streaming",
        "disney+",
        "theatrical",
        "streaming film",
        "franchise/ip",
        "premium entertainment",
        "product development",
        "workflow",
        "governance",
        "milestones",
        "quality",
        "vendor",
        "technology",
        "analytics",
        "creative",
        "multimillion-dollar",
    )
    keywords = [str(keyword) for keyword in parsed_job.get("keywords", [])]
    priorities = PROFILE_PRIORITIES[resume_profile] + sample_priorities
    if is_google_youtube_role(parsed_job):
        priorities += (
            "google advertising products",
            "google and youtube",
            "youtube",
            "product activation",
            "measurement readiness",
            "large entertainment advertisers",
            "platform activation",
            "stakeholder alignment",
            "operational excellence",
        )

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
        if len(selected) == 6:
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


def _project_relevance_score(project_name: str, parsed_job: Dict[str, Any]) -> int:
    text = " ".join(
        _flatten_strings(
            [parsed_job.get("job_title"), parsed_job.get("raw_text"), parsed_job.get("job_description"), parsed_job.get("keywords", [])]
        )
    )
    project_terms = PROJECT_RELEVANCE_TERMS.get(project_name, ())
    normalized = _normalize_text(text)
    return sum(1 for term in project_terms if _normalize_text(term) in normalized)


def _selected_projects(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    resume_profile: str,
    complete_foundation: bool = False,
) -> List[Tuple[Dict[str, Any], List[str]]]:
    projects = career_data["data"]["projects"].get("projects", [])
    if complete_foundation:
        return [
            (
                project,
                _dedupe(
                    [
                        str(project.get("summary") or ""),
                        *[
                            str(highlight)
                            for highlight in project.get("highlights", [])
                        ],
                    ]
                ),
            )
            for project in projects
        ]

    ranked: List[Tuple[int, Dict[str, Any], List[str]]] = []
    plan = material_editing_plan(parsed_job)
    category = plan.get("role_category")
    section_rules = plan.get("resume_section_rules", {})
    creative_rule = section_rules.get("creative_editorial_projects")
    campaignos_rule = section_rules.get("campaignos")

    for project in projects:
        name = str(project.get("name") or "")
        score = _project_relevance_score(name, parsed_job)
        if score < 2:
            continue
        if creative_rule == "omit" and name in {"OMG23 Multiverse Newsletter", "RoboXT Studios"}:
            continue
        if category in {"chief_of_staff_business_operations", "traditional_pmo_governance"} and name in {"OMG23 Multiverse Newsletter", "RoboXT Studios"}:
            continue
        if name == "CampaignOS":
            bullets = _campaignos_bullets(career_data)
            if campaignos_rule == "supporting":
                bullets = bullets[:1]
        else:
            bullets = [project.get("summary", "")]
            limit = 1
            bullets.extend(project.get("highlights", [])[:limit])
            bullets = _dedupe([str(bullet) for bullet in bullets if bullet])
        if name == "Career Catalyst" and "product operations" in _normalize_text(str(parsed_job.get("raw_text") or "")):
            score += 4
        ranked.append((score, project, bullets))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
    return [(project, bullets[:2]) for _score, project, bullets in ranked[:2]]


def _relevant_associated_evidence(
    projects: List[Dict[str, Any]], parsed_job: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Keep prospect-scoped Evidence only when its stored language overlaps the role."""
    role_text = _normalize_text(
        " ".join(_flatten_strings([parsed_job.get("job_title"), parsed_job.get("raw_text"), parsed_job.get("keywords", [])]))
    )
    role_terms = set(role_text.split()) - {"and", "the", "for", "with", "from", "role"}
    ranked = []
    for project in projects:
        terms = _flatten_strings(
            [project.get("title"), project.get("function"), project.get("project_type"), project.get("actions"), project.get("results"), project.get("skills", []), project.get("technologies", []), project.get("tags", [])]
        )
        evidence_terms = set(_normalize_text(" ".join(terms)).split()) - {"and", "the", "for", "with", "from", "role", "built"}
        score = len(role_terms & evidence_terms)
        if score:
            ranked.append((score, project))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    return [project for _score, project in ranked[:2]]


def _earlier_career_positions(
    career_data: Dict[str, Any], parsed_job: Dict[str, Any], *, complete_foundation: bool
) -> List[Dict[str, Any]]:
    positions = career_data["data"]["positions"].get("positions", [])
    earlier = [
        position
        for position in positions
        if "OMG23" not in str(position.get("company") or "")
    ]
    if complete_foundation:
        return earlier
    if is_ai_transformation_role(parsed_job):
        return []
    role_text = _normalize_text(
        " ".join(_flatten_strings([parsed_job.get("job_title"), parsed_job.get("raw_text")]))
    )
    production_signals = (
        "production", "trafficking", "broadcast", "studio asset", "video", "post production"
    )
    selected = []
    if any(term in role_text for term in ("media", "marketing", "advertising", "campaign")):
        selected.extend(
            position
            for position in earlier
            if str(position.get("company")) in {"Intermedia Advertising", "US International Media"}
        )
    if any(term in role_text for term in production_signals):
        selected.extend(
            position for position in earlier if str(position.get("company")) == "Additional Early Experience"
        )
    return _dedupe_positions(selected)


def _dedupe_positions(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for position in positions:
        key = str(position.get("company") or "")
        if key and key not in seen:
            seen.add(key)
            result.append(position)
    return result


def _include_professional_development(parsed_job: Dict[str, Any]) -> bool:
    text = _normalize_text(
        " ".join(_flatten_strings([parsed_job.get("job_title"), parsed_job.get("raw_text")]))
    )
    return any(term in text for term in ("certification required", "certified", "professional development"))


def _professional_development(career_data: Dict[str, Any]) -> List[str]:
    certification_lines = []
    for certification in career_data["data"]["certifications"].get("certifications", []):
        areas = ", ".join(certification.get("areas", []))
        certification_lines.append(f"{certification.get('provider')}: {areas}")

    focus_areas = career_data["data"]["personal_brand"].get("current_focus", [])
    if focus_areas:
        certification_lines.append("Current focus: " + ", ".join(focus_areas))

    return certification_lines


def _render_markdown(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    match_report: Dict[str, Any],
    resume_profile: str,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    complete_foundation: bool = False,
) -> str:
    personal_brand = career_data["data"]["personal_brand"]
    candidate = personal_brand["candidate"]
    competencies = (
        _all_skills(career_data)
        if complete_foundation
        else _select_core_competencies(
            career_data,
            parsed_job,
            match_report,
            resume_profile,
        )
    )
    platforms = (
        _platform_categories(career_data)
        if complete_foundation
        else _selected_platform_categories(career_data, parsed_job, resume_profile)
    )
    positions = career_data["data"]["positions"].get("positions", [])
    omg_position = next(
        (position for position in positions if "OMG23" in position.get("company", "")),
        positions[0] if positions else {},
    )
    experience_bullets = (
        _dedupe([str(value) for value in omg_position.get("highlights", [])])
        if complete_foundation
        else _select_experience_bullets(career_data, parsed_job, resume_profile)
    )
    selected_projects = _selected_projects(
        career_data,
        parsed_job,
        resume_profile,
        complete_foundation=complete_foundation,
    )
    associated_evidence_projects = _relevant_associated_evidence(
        associated_evidence_projects or [], parsed_job
    )
    earlier_positions = _earlier_career_positions(
        career_data, parsed_job, complete_foundation=complete_foundation
    )
    development = (
        _professional_development(career_data)
        if complete_foundation or _include_professional_development(parsed_job)
        else []
    )

    lines = [
        f"<!-- career-catalyst-job-title: {parsed_job.get('job_title') or 'Role'} -->",
        f"<!-- career-catalyst-company: {parsed_job.get('company') or 'Company'} -->",
        "",
        f"# {candidate.get('name', 'Trisha Lynch')}",
        "",
        candidate.get("headline", ""),
        "",
        _contact_line(personal_brand),
        "",
        "## Profile",
        "",
        _profile_summary(
            career_data,
            match_report,
            competencies,
            resume_profile,
            parsed_job,
        ),
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
        progression = " | ".join(omg_position.get("progression", []))
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

    if selected_projects or associated_evidence_projects:
        project_heading = (
            "Selected Products & Independent Work"
            if complete_foundation
            else "Relevant Projects & Impact"
        )
        lines.extend([f"## {project_heading}", ""])
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

    for project in associated_evidence_projects:
        context = " · ".join(
            str(value)
            for value in (project.get("employer"), project.get("client") or project.get("business_unit"), project.get("project_type"))
            if value
        )
        lines.extend([f"### {project.get('title')}", "", context or "Verified role-associated evidence", ""])
        if project.get("actions"):
            lines.append(f"- {project.get('actions')}")
        if project.get("results"):
            lines.append(f"- {project.get('results')}")
        lines.append("")

    if earlier_positions:
        lines.extend(["## Earlier Career", ""])
    for earlier_position in earlier_positions:
        progression = " | ".join(earlier_position.get("progression", []))
        metadata = " | ".join(
            str(value)
            for value in (
                earlier_position.get("location"),
                earlier_position.get("timeframe"),
            )
            if value
        )
        lines.extend(
            [
                f"### {earlier_position.get('company')}",
                "",
                metadata,
                "",
                progression,
                "",
            ]
        )
        earlier_highlights = (
            earlier_position.get("highlights", [])
            if complete_foundation
            else [earlier_position.get("summary", "")]
        )
        if not is_google_youtube_role(parsed_job):
            earlier_highlights = [
                highlight
                for highlight in earlier_highlights
                if "Google advertising products" not in str(highlight)
            ]
        lines.extend(f"- {highlight}" for highlight in earlier_highlights)
        lines.append("")

    if development:
        lines.extend(["## Professional Development", ""])
        lines.extend(f"- {line}" for line in development)
        lines.append("")

    return "\n".join(line for line in lines if line is not None)


def render_base_resume(project_root: Optional[PathInput] = None) -> str:
    """Render the complete Golden Master-aligned foundation without writing files."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    career_data = load_resume_foundation(root)
    parsed_job = {
        "company": "Career Catalyst",
        "job_title": "Golden Master Resume",
        "raw_text": "operations transformation media operations martech AI systems entertainment",
        "keywords": [
            "operations transformation",
            "media operations",
            "martech",
            "AI systems",
            "entertainment",
        ],
    }
    markdown = cleanup_repeated_words(
        _render_markdown(
            career_data,
            parsed_job,
            {"keyword_matches": [], "transferable_strengths": []},
            "executive_operations",
            [],
            complete_foundation=True,
        )
    )
    markdown, _rewrite_notes = rewrite_banned_voice_phrases(markdown)
    validate_public_career_claims(markdown)
    try:
        validate_candidate_language(markdown, context="Generated base resume")
    except CandidateLanguageError as error:
        raise ResumeTailoringError(str(error)) from error
    return markdown


def tailor_resume(
    resume_profile: str,
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate and save a tailored Markdown resume."""
    if resume_profile not in VALID_RESUME_PROFILES:
        valid = ", ".join(VALID_RESUME_PROFILES)
        raise ResumeTailoringError(f"Unknown resume profile '{resume_profile}'. Valid profiles: {valid}")

    root = Path(project_root) if project_root is not None else Path.cwd()
    career_data = load_resume_foundation(root)
    associated_evidence_projects = associated_evidence_projects or []
    verified_evidence_context = evidence_generation_context(associated_evidence_projects)
    parsed_job = parse_job_description(root / job_path)
    match_report = score_job_match(job_path, root)
    markdown = cleanup_repeated_words(
        _render_markdown(career_data, parsed_job, match_report, resume_profile, associated_evidence_projects)
    )
    markdown, rewrite_notes = rewrite_banned_voice_phrases(markdown)
    validate_public_career_claims(markdown)
    banned_phrases = list(career_data["config"].get("voice", {}).get("avoid", []))
    banned_phrases.extend(load_writing_voice_profile(root).get("banned_phrases", []))
    banned_phrases.extend(material_editing_plan(parsed_job, root).get("banned_phrases", []))
    remaining_banned = remaining_banned_voice_phrases(markdown, banned_phrases)
    if remaining_banned:
        raise ResumeTailoringError(
            f"Generated tailored resume contains banned voice phrase: {remaining_banned[0]}"
        )
    try:
        validate_candidate_language(markdown, context="Generated tailored resume")
    except CandidateLanguageError as error:
        raise ResumeTailoringError(str(error)) from error
    validate_material_context(markdown, parsed_job, "Tailored_Resume")

    export_dir = root / "exports" / "internal" / "resumes"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / build_upload_filename(
        "Trisha Lynch",
        str(parsed_job.get("job_title") or "Role"),
        str(parsed_job.get("company") or "Company"),
        resume_profile if resume_profile in {"ats_resume", "styled_resume"} else "ats_resume",
        "md",
    )
    output_path.write_text(markdown, encoding="utf-8")
    text_path = output_path.with_suffix(".txt")
    text_path.write_text(markdown, encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "resume_profile": resume_profile,
        "recommended_resume_profile": match_report.get("recommended_resume_profile"),
        "match_score": match_report.get("match_score"),
        "match_band": match_report.get("match_band"),
        "tailoring_notes": match_report.get("tailoring_notes", []),
        "output_path": str(output_path),
        "txt_output_path": str(text_path),
        "warnings": (
            [
                "Rewrote banned voice phrases before validation: "
                + ", ".join(note["phrase"] for note in rewrite_notes)
            ]
            if rewrite_notes
            else []
        ),
        "banned_phrase_rewrites": rewrite_notes,
        "associated_evidence_project_titles": [
            str(project.get("title")) for project in (associated_evidence_projects or [])
        ],
        "associated_evidence_context": verified_evidence_context,
    }
