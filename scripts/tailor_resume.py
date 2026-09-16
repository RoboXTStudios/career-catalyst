"""Generate tailored Markdown resumes from structured Career Catalyst data."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

try:
    from .application_strategy import evidence_priorities
    from .employer_identity import normalize_applicant_employer_names
    from .filename_utils import build_upload_filename
    from .load_data import load_all_yaml
    from .evidence_engine import load_writing_voice_profile
    from .evidence_profile import load_evidence_profile, select_profile_evidence
    from .role_evidence_selection import selected_evidence
    from .human_positioning import (
        professional_summary,
        validate_applicant_evidence,
        validate_human_positioning,
    )
    from .parse_job import parse_job_description
    from .package_context import validate_material_context
    from .role_lens import classify_role_lens, enforce_role_lens_quality
    from .role_context import is_google_youtube_role
    from .role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from .score_match import score_job_match
    from .text_cleanup import cleanup_repeated_words
except ImportError:
    from application_strategy import evidence_priorities
    from employer_identity import normalize_applicant_employer_names
    from filename_utils import build_upload_filename
    from load_data import load_all_yaml
    from evidence_engine import load_writing_voice_profile
    from evidence_profile import load_evidence_profile, select_profile_evidence
    from role_evidence_selection import selected_evidence
    from human_positioning import (
        professional_summary,
        validate_applicant_evidence,
        validate_human_positioning,
    )
    from parse_job import parse_job_description
    from package_context import validate_material_context
    from role_lens import classify_role_lens, enforce_role_lens_quality
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

PEOPLE_OPERATIONS_TRANSFERABLE_COMPETENCIES = (
    "Cross-Functional Leadership",
    "Team Enablement",
    "Change Management",
    "Stakeholder Communication",
    "Ownership & Responsibility Clarity",
    "Process Implementation",
    "Workflow Governance",
    "Operational Consistency",
    "Executive Communication",
    "Continuous Improvement",
)

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

PathInput = Union[str, Path]
RESUME_EVIDENCE_LIMIT = 4


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
    resume_evidence: Sequence[Dict[str, Any]] = (),
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
    evidence_competencies = _dedupe(
        str(skill)
        for item in resume_evidence
        for skill in item.get("skills") or []
        if str(skill).strip()
    )
    job_text = _normalize_text(str(parsed_job.get("raw_text") or ""))
    talent_requested = any(
        signal in job_text
        for signal in (
            "people leadership",
            "talent development",
            "team building",
            "coaching",
            "organizational development",
            "team leadership",
        )
    )
    competency_order = {
        competency: index for index, competency in enumerate(evidence_competencies)
    }
    evidence_competencies.sort(
        key=lambda skill: (
            -(
                (20 if _normalize_text(skill) in job_text else 0)
                + (
                    15
                    if talent_requested
                    and any(
                        signal in _normalize_text(skill)
                        for signal in ("people leadership", "coaching", "team leadership")
                    )
                    else 0
                )
                + len(set(_normalize_text(skill).split()) & set(job_text.split()))
            ),
            competency_order[skill],
        )
    )
    # Evidence enriches the role-tailored competency set without crowding it out.
    selected = evidence_competencies[:6] + selected
    if classify_role_lens(parsed_job)["primary"] == "people_operations":
        selected = list(PEOPLE_OPERATIONS_TRANSFERABLE_COMPETENCIES) + selected
    if is_google_youtube_role(parsed_job):
        selected = list(GOOGLE_YOUTUBE_COMPETENCIES) + selected
    if len(selected) < 8:
        selected.extend(skills)
    return _dedupe(selected)[:12]


def _platform_categories(career_data: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    categories = career_data["data"]["platforms"].get("platform_categories", [])
    return [
        (
            str(category["name"]),
            [
                str(item)
                for item in category.get("items", [])
                if str(item).strip().lower() != "substack"
            ],
        )
        for category in categories
        if isinstance(category, dict) and category.get("name")
    ]


def _profile_summary(
    career_data: Dict[str, Any],
    match_report: Dict[str, Any],
    competencies: Sequence[str],
    resume_profile: str,
    parsed_job: Dict[str, Any],
) -> str:
    if classify_role_lens(parsed_job)["primary"] == "people_operations":
        summary = (
            "Operations leader known for improving how cross-functional teams communicate, "
            "understand ownership, and adopt practical ways of working. Builds clear workflows, "
            "usable standards, and dependable communication practices that reduce day-to-day "
            "friction while helping teams execute business priorities with clarity."
        )
        validate_human_positioning(summary, "professional summary")
        return summary
    profile_key = "google_youtube_operations" if is_google_youtube_role(parsed_job) else resume_profile
    configured = (
        career_data["data"]
        .get("personal_brand", {})
        .get("career_profile", {})
        .get("profile_summaries", {})
        .get(profile_key)
    )
    summary = str(configured or professional_summary(resume_profile, parsed_job, competencies))
    validate_human_positioning(summary, "professional summary")
    return summary


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
    people_operations = classify_role_lens(parsed_job)["primary"] == "people_operations"
    if people_operations:
        deduped = _dedupe(candidate_bullets)
        preferred_starts = (
            "Led cross-functional teams of 60+",
            "Introduced scalable workflows",
            "Aligned creative, marketing, media, analytics, technology, and operations teams",
            "Established workflows, milestones, quality standards, and partner coordination",
            "Partnered across creative, marketing, media, analytics, engineering, technology, operations",
            "Created and served as Managing Editor of Multiverse",
            "Advanced from Campaign Manager to Group Director",
        )
        return [
            next(bullet for bullet in deduped if bullet.startswith(prefix))
            for prefix in preferred_starts
            if any(bullet.startswith(prefix) for bullet in deduped)
        ]

    sample_priorities = (
        "60+",
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
    role_interpretation = parsed_job.get("role_interpretation") or {}
    interpreted_archetype = (
        str(role_interpretation.get("primary_archetype") or "")
        if isinstance(role_interpretation, dict)
        else ""
    )
    priorities += tuple(
        value.replace("_", " ") for value in evidence_priorities(interpreted_archetype)
    )
    if people_operations:
        priorities += (
            "60+",
            "cross-functional teams",
            "aligned",
            "workflow",
            "standards",
            "ownership",
            "partnered",
            "employee storytelling",
            "communication",
        )
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
        if people_operations and any(
            term in bullet.lower()
            for term in (
                "google and youtube",
                "advertising platform",
                "multimillion-dollar",
                "campaign activation",
            )
        ):
            continue
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
    plan = material_editing_plan(parsed_job)
    category = plan.get("role_category")
    section_rules = plan.get("resume_section_rules", {})
    creative_rule = section_rules.get("creative_editorial_projects")

    for project in projects:
        name = project.get("name")
        if name in {"CampaignOS", "Substack Writer"} or not _project_is_relevant(str(name), parsed_job, resume_profile):
            continue
        if creative_rule == "omit" and name in {"Substack Writer", "OMG23 Multiverse Newsletter"}:
            continue
        if category in {"chief_of_staff_business_operations", "traditional_pmo_governance"} and name in {"Substack Writer", "OMG23 Multiverse Newsletter"}:
            continue
        bullets = [project.get("summary", "")]
        limit = 1 if creative_rule == "minimize" else 3
        bullets.extend(project.get("highlights", [])[:limit])
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


def _render_markdown(
    career_data: Dict[str, Any],
    parsed_job: Dict[str, Any],
    match_report: Dict[str, Any],
    resume_profile: str,
    resume_evidence: Sequence[Dict[str, Any]] = (),
) -> str:
    personal_brand = career_data["data"]["personal_brand"]
    candidate = personal_brand["candidate"]
    competencies = _select_core_competencies(
        career_data,
        parsed_job,
        match_report,
        resume_profile,
        resume_evidence,
    )
    platforms = _platform_categories(career_data)
    if classify_role_lens(parsed_job)["primary"] == "people_operations":
        platforms = [
            item for item in platforms if item[0] != "AdTech & Measurement"
        ]
    positions = career_data["data"]["positions"].get("positions", [])
    omg_position = next(
        (position for position in positions if "OMG23" in position.get("company", "")),
        positions[0] if positions else {},
    )
    experience_bullets = _select_experience_bullets(career_data, parsed_job, resume_profile)
    professional_evidence = [
        str(item.get("description") or "").strip()
        for item in resume_evidence
        if "omg23" in _normalize_text(
            f"{item.get('career_period') or ''} {item.get('company') or ''}"
        )
        and str(item.get("description") or "").strip()
    ]
    experience_bullets = _dedupe([*professional_evidence, *experience_bullets])[:10]
    independent_evidence = [
        str(item.get("description") or "").strip()
        for item in resume_evidence
        if str(item.get("description") or "").strip()
        and str(item.get("description") or "").strip() not in professional_evidence
    ]
    selected_projects = _selected_projects(career_data, parsed_job, resume_profile)
    earlier_position = _earlier_career(career_data)
    development = _professional_development(career_data)

    lines = [
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

    if independent_evidence:
        lines.extend(["## Selected Impact", ""])
        lines.extend(f"- {bullet}" for bullet in independent_evidence)
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
        earlier_highlights = earlier_position.get("highlights", [])
        if not is_google_youtube_role(parsed_job):
            earlier_highlights = [
                highlight
                for highlight in earlier_highlights
                if "Google advertising products" not in str(highlight)
            ]
        lines.extend(f"- {highlight}" for highlight in earlier_highlights)
        lines.append("")

    lines.extend(["## Professional Development", ""])
    lines.extend(f"- {line}" for line in development)
    lines.append("")

    return normalize_applicant_employer_names(
        "\n".join(line for line in lines if line is not None)
    )


def tailor_resume(
    resume_profile: str,
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a tailored Markdown resume."""
    if resume_profile not in VALID_RESUME_PROFILES:
        valid = ", ".join(VALID_RESUME_PROFILES)
        raise ResumeTailoringError(f"Unknown resume profile '{resume_profile}'. Valid profiles: {valid}")

    root = Path(project_root) if project_root is not None else Path.cwd()
    career_data = load_all_yaml(root)
    parsed_job = parse_job_description(root / job_path)
    package_context = dict(package_context or {})
    career_coach = dict(package_context.get("career_coach") or {})
    coach_emphasis = [
        str(value).strip()
        for value in career_coach.get("lead_with") or []
        if str(value).strip()
    ]
    if coach_emphasis:
        parsed_job["keywords"] = list(
            dict.fromkeys([*(parsed_job.get("keywords") or []), *coach_emphasis])
        )
    role_interpretation = dict(package_context.get("role_interpretation") or {})
    evidence_selection_overrides = dict(
        package_context.get("evidence_selection_overrides")
        or (package_context.get("role_evidence_selection") or {}).get("overrides")
        or {}
    )
    match_report = (
        score_job_match(
            job_path, root, role_interpretation, evidence_selection_overrides or None
        )
        if role_interpretation
        else score_job_match(
            job_path, root, evidence_selection_overrides=evidence_selection_overrides or None
        )
    )
    parsed_job["role_interpretation"] = dict(
        match_report.get("role_interpretation") or role_interpretation
    )
    role_selected = selected_evidence(match_report.get("role_evidence_selection") or {})
    manual_evidence = [
        item for item in role_selected if item.get("selected_by") == "User override"
    ]
    automatic_evidence = [
        item for item in role_selected if item.get("selected_by") != "User override"
    ]
    resume_evidence = [
        item
        for item in [*manual_evidence, *automatic_evidence]
        if item.get("selected_by") == "User override"
        or (item.get("recommended_usage") or {}).get("resume", True)
    ][:RESUME_EVIDENCE_LIMIT]
    markdown = cleanup_repeated_words(
        _render_markdown(
            career_data,
            parsed_job,
            match_report,
            resume_profile,
            resume_evidence,
        )
    )
    evidence_profile = load_evidence_profile(root)
    resume_recommendations = [
        item for item in resume_evidence
        if item.get("resume_visibility") != "Fully Represented"
        and (
            item.get("selected_by") == "User override"
            or (item.get("recommended_usage") or {}).get("resume_recommendations", True)
        )
    ]
    if not resume_recommendations:
        resume_recommendations = [
            item for item in select_profile_evidence(
                {
                    **parsed_job,
                    "primary_archetype": (parsed_job.get("role_interpretation") or {}).get("primary_archetype"),
                },
                evidence_profile,
                usage="resume_recommendations",
                max_items=8,
            )
            if item.get("resume_visibility") != "Fully Represented"
        ]
    role_lens = classify_role_lens(parsed_job)
    markdown, role_lens_quality = enforce_role_lens_quality(
        markdown, role_lens, material_type="resume"
    )
    if not role_lens_quality["valid"]:
        raise ResumeTailoringError(
            f"Generated resume does not match role lens: {role_lens_quality['violations'][0]['code']}"
        )
    markdown, rewrite_notes = rewrite_banned_voice_phrases(markdown)
    validate_applicant_evidence(markdown, "tailored resume")
    banned_phrases = list(career_data["config"].get("voice", {}).get("avoid", []))
    banned_phrases.extend(load_writing_voice_profile(root).get("banned_phrases", []))
    banned_phrases.extend(material_editing_plan(parsed_job, root).get("banned_phrases", []))
    remaining_banned = remaining_banned_voice_phrases(markdown, banned_phrases)
    if remaining_banned:
        raise ResumeTailoringError(
            f"Generated tailored resume contains banned voice phrase: {remaining_banned[0]}"
        )
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
        "role_lens": role_lens,
        "role_lens_quality": role_lens_quality,
        "role_interpretation": parsed_job.get("role_interpretation", {}),
        "resume_emphasis": coach_emphasis
        or evidence_priorities(
            (parsed_job.get("role_interpretation") or {}).get("primary_archetype")
        ),
        "career_coach": career_coach,
        "evidence_profile_recommendations": resume_recommendations,
        "resume_selected_evidence": resume_evidence,
        "resume_evidence_limit": RESUME_EVIDENCE_LIMIT,
        "evidence_gap_analysis": match_report.get("evidence_gap_analysis", {}),
        "role_evidence_selection": match_report.get("role_evidence_selection", {}),
    }
