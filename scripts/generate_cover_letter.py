"""Generate grounded cover letters from Career Catalyst data and job analysis."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .load_data import load_all_yaml
    from .parse_job import parse_job_description
    from .score_match import score_job_match
    from .text_cleanup import cleanup_repeated_words
except ImportError:
    from load_data import load_all_yaml
    from parse_job import parse_job_description
    from score_match import score_job_match
    from text_cleanup import cleanup_repeated_words


PathInput = Union[str, Path]


class ApplicationMaterialError(Exception):
    """Raised when an application material cannot be generated safely."""


def load_generation_context(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Load career data, parsed job details, and the match report."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    resolved_job_path = Path(job_path)
    if not resolved_job_path.is_absolute():
        resolved_job_path = root / resolved_job_path

    career_data = load_all_yaml(root)
    return {
        "root": root,
        "career_data": career_data,
        "voice": career_data["config"].get("voice", {}),
        "parsed_job": parse_job_description(resolved_job_path),
        "match_report": score_job_match(job_path, root),
    }


def _slug(value: Optional[str], fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value or "").strip("_")
    return slug or fallback


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


def save_material(
    context: Dict[str, Any],
    suffix: str,
    content: str,
    minimum_words: int,
    maximum_words: int,
) -> Dict[str, Any]:
    """Validate and save one Markdown application material."""
    content = cleanup_repeated_words(content)
    if "—" in content:
        raise ApplicationMaterialError("Generated application materials must not contain em dashes.")
    if "placeholder" in content.lower():
        raise ApplicationMaterialError("Generated application materials must not contain placeholder text.")

    lowered_content = content.lower()
    for phrase in context.get("voice", {}).get("avoid", []):
        if str(phrase).lower() in lowered_content:
            raise ApplicationMaterialError(
                f"Generated application materials contain banned voice phrase: {phrase}"
            )

    word_count = _word_count(content)
    if not minimum_words <= word_count <= maximum_words:
        raise ApplicationMaterialError(
            f"Generated {suffix} must be {minimum_words}-{maximum_words} words; got {word_count}."
        )

    parsed_job = context["parsed_job"]
    company_slug = _slug(parsed_job.get("company"), "Company")
    role_slug = _slug(parsed_job.get("job_title"), "Role")
    output_path = (
        context["root"]
        / "exports"
        / "messages"
        / f"Trisha_Lynch_{company_slug}_{role_slug}_{suffix}.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "match_score": context["match_report"].get("match_score"),
        "output_path": str(output_path),
        "word_count": word_count,
    }


def _join_human(values: List[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _job_focus(parsed_job: Dict[str, Any]) -> str:
    if _is_creative_product_operations_role(parsed_job):
        return "global creative operations, product development, and cross-functional execution"

    preferred = (
        "enterprise strategy",
        "operational planning",
        "cross-functional",
        "process improvement",
        "stakeholder alignment",
        "executive communication",
    )
    keywords = [str(keyword).lower() for keyword in parsed_job.get("keywords", [])]
    selected = [term for term in preferred if term in keywords][:3]
    if not selected:
        selected = keywords[:3]
    display_terms = {
        "cross-functional": "cross-functional execution",
    }
    selected = [display_terms.get(term, term) for term in selected]
    return _join_human(selected) or "strategy and execution"


def _is_creative_product_operations_role(parsed_job: Dict[str, Any]) -> bool:
    text = " ".join(
        str(value)
        for value in (
            parsed_job.get("job_title", ""),
            parsed_job.get("raw_text", ""),
        )
    ).lower()
    creative_signals = ("creative operations", "creative leadership", "creative assets")
    product_signals = ("product development", "licensed merchandise", "licensing")
    return any(signal in text for signal in creative_signals) and any(
        signal in text for signal in product_signals
    )


def _as_first_person(statement: str) -> str:
    text = statement.strip()
    if not text or text.startswith("I "):
        return text
    return "I " + text[0].lower() + text[1:]


def _achievement(career_data: Dict[str, Any], achievement_id: str) -> str:
    achievements = career_data["data"]["achievements"].get("achievements", [])
    achievement = next(
        (item for item in achievements if item.get("id") == achievement_id),
        {},
    )
    return str(achievement.get("statement", "")).strip()


def _position(career_data: Dict[str, Any], company_fragment: str) -> Dict[str, Any]:
    positions = career_data["data"]["positions"].get("positions", [])
    return next(
        (item for item in positions if company_fragment in str(item.get("company", ""))),
        {},
    )


def _project(career_data: Dict[str, Any], project_name: str) -> Dict[str, Any]:
    projects = career_data["data"]["projects"].get("projects", [])
    return next((item for item in projects if item.get("name") == project_name), {})


def _entertainment_scope(career_data: Dict[str, Any]) -> str:
    position = _position(career_data, "OMG23")
    return next(
        (
            str(highlight)
            for highlight in position.get("highlights", [])
            if "Disney Studios Theatrical" in str(highlight)
        ),
        "",
    )


def _employer_names(position: Dict[str, Any]) -> tuple[str, str]:
    """Return the full employer name and a safe shorthand for later mentions."""
    full_name = str(position.get("company") or "OMG23 / OMD Entertainment")
    shorthand = "OMG23" if "OMG23" in full_name else full_name
    return full_name, shorthand


def _validate_cover_letter_repetition(content: str) -> None:
    phrase_limits = {
        "campaign operations": 1,
        "complex": 1,
        "cross-functional": 1,
    }
    for paragraph in content.split("\n\n"):
        lowered = paragraph.lower()
        for phrase, maximum in phrase_limits.items():
            if lowered.count(phrase) > maximum:
                raise ApplicationMaterialError(
                    f"Cover letter paragraph repeats '{phrase}' too many times."
                )
        if "role role" in lowered:
            raise ApplicationMaterialError("Cover letter paragraph contains repeated role wording.")


def _campaignos_is_relevant(context: Dict[str, Any]) -> bool:
    top_projects = context["match_report"].get("top_matching_projects", [])
    if any(project.get("name") == "CampaignOS" for project in top_projects):
        return True

    text = " ".join(
        str(value)
        for value in (
            context["parsed_job"].get("job_title", ""),
            *context["parsed_job"].get("keywords", []),
        )
    ).lower()
    return any(term in text for term in ("ai", "automation", "systems", "workflow", "product"))


def _cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    job_focus = _job_focus(parsed_job)

    position = _position(career_data, "OMG23")
    position_company, position_shorthand = _employer_names(position)

    campaignos = _project(career_data, "CampaignOS")
    campaignos_summary = str(campaignos.get("summary", "")).strip()

    if role:
        opening_sentence = (
            f"The {role} role at {company} stood out because it brings {job_focus} together "
            "in a global entertainment organization."
        )
    else:
        opening_sentence = (
            f"This opportunity at {company} stood out because it brings {job_focus} together "
            "in a global entertainment organization."
        )

    opening = (
        f"{opening_sentence} What caught my attention is the "
        "practical challenge behind the title: helping many functions turn complex priorities into "
        "clear workflows, aligned milestones, useful standards, and reliable execution. I have spent "
        "much of my career helping creative and marketing teams build that kind of clarity without "
        "slowing down the work."
    )

    experience = (
        "Much of my career has been spent helping creative, marketing, media, analytics, and "
        "technology teams bring structure to complex theatrical and streaming campaign ecosystems. "
        f"At {position_company}, my primary focus was Disney Studios Theatrical and Disney "
        "Streaming/DSS work, supporting campaign operations across Pixar, Lucasfilm, Marvel, 20th "
        "Century Studios, Searchlight Pictures, Disney+, and franchise/IP priorities. That work "
        "required close coordination across internal teams and external partners, with clear "
        "workflows, milestones, quality standards, and consistent execution at scale."
    )

    if _campaignos_is_relevant(context) and campaignos_summary:
        transformation = (
            f"The systems mindset I developed at {position_shorthand} also led me to build "
            f"CampaignOS. As {campaignos.get('role')}, I "
            f"{campaignos_summary[0].lower() + campaignos_summary[1:]} The project grew from a "
            "practical question I have encountered repeatedly: how can teams reduce manual effort "
            "and operational risk while improving visibility and decision-making? That mix of "
            "strategy, systems thinking, and hands-on execution is where I do my best work."
        )
    else:
        workflow = _achievement(career_data, "workflow_governance")
        transformation = (
            f"I have also focused on improving the systems behind the work. {_as_first_person(workflow)} "
            "That experience has shaped a practical approach to operational transformation, "
            "with clear ownership, useful standards, and room for creative teams to do their best work."
        )

    if _is_creative_product_operations_role(parsed_job):
        closing = (
            "What appeals to me about this opportunity is the chance to help creative and product "
            f"development teams at {company} turn entertainment IP and franchise priorities into "
            "clear, scalable operating rhythms. I would welcome the chance to learn more about the "
            "team's priorities and discuss how I could contribute."
        )
    else:
        closing = (
            f"What appeals to me about this opportunity is the chance to bring that experience into "
            f"{company} within a complex entertainment organization. I would welcome the chance "
            "to learn more about the team's priorities and discuss how I could contribute."
        )

    content = "\n\n".join(
        ["Hello,", opening, experience, transformation, closing, "Best,\n\nTrisha Lynch"]
    )
    _validate_cover_letter_repetition(content)
    return content


def generate_cover_letter(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate and save a concise Markdown cover letter."""
    context = load_generation_context(job_path, project_root)
    return save_material(
        context,
        "Cover_Letter",
        _cover_letter_content(context),
        minimum_words=250,
        maximum_words=400,
    )
