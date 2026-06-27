"""Generate grounded recruiter and hiring manager messages."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _campaignos_is_relevant,
        _entertainment_scope,
        _job_focus,
        _position,
        _project,
        load_generation_context,
        save_material,
    )
    from .role_context import is_google_youtube_role
except ImportError:
    from generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _campaignos_is_relevant,
        _entertainment_scope,
        _job_focus,
        _position,
        _project,
        load_generation_context,
        save_material,
    )
    from role_context import is_google_youtube_role


PathInput = Union[str, Path]
MESSAGE_TYPES = ("recruiter", "hiring_manager")


def _recruiter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"the {role} role" if role else "this opportunity"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]
    entertainment_scope = _entertainment_scope(career_data)
    campaignos = _project(career_data, "CampaignOS")

    if is_google_youtube_role(parsed_job):
        message = (
            f"I'm reaching out about {role_reference} at {company}. It stands out because it "
            "connects YouTube product activation, GTM operations, and large advertiser execution. "
            "I bring long-term hands-on experience with Google advertising products, including "
            "YouTube, dating back to the early 2000s. I have translated Google and YouTube platform "
            "capabilities into campaign execution, measurement readiness, and operational workflows "
            "across large entertainment advertisers. CampaignOS is a current proof point for how I "
            "turn recurring operational needs into scalable systems."
        )
        question = (
            "If you're the right person to speak with, I would be glad to share more. If not, would "
            "you mind pointing me in the right direction?"
        )
        return "\n\n".join(["Hello,", message, question, "Best,\n\nTrisha Lynch"])

    message = (
        f"I'm reaching out about {role_reference} at {company}. It stands out because it "
        f"connects {_job_focus(parsed_job)} around entertainment IP. At {position_company}, "
        f"{_as_first_person(entertainment_scope)} I led cross-functional teams of 60+ and built "
        "workflows, quality practices, and operating standards for entertainment campaigns."
    )
    if _campaignos_is_relevant(context) and campaignos:
        message += " I also built CampaignOS to turn operational challenges into scalable systems."
    question = (
        "If you're the right person to speak with, I would be glad to share more. If not, would "
        "you mind pointing me in the right direction?"
    )
    return "\n\n".join(["Hello,", message, question, "Best,\n\nTrisha Lynch"])


def _hiring_manager_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    campaignos = _project(career_data, "CampaignOS")
    entertainment_scope = _entertainment_scope(career_data)

    if is_google_youtube_role(parsed_job):
        opening = (
            f"{role_reference} at {company} stood out because it brings YouTube product activation, "
            "GTM operations, seller enablement, and large advertiser execution together. Translating "
            "platform priorities into clear activation strategies, feedback loops, and measurable "
            "execution is work I find meaningful."
        )
        experience = (
            "I bring long-term hands-on experience with Google advertising products, including "
            "YouTube, dating back to the early 2000s. Across large entertainment advertisers, I have "
            "connected brand objectives, campaign operations, measurement readiness, and platform "
            "activation while aligning marketing, media, analytics, technology, and senior stakeholders. "
            "Disney Studios Theatrical and Disney Streaming/DSS work provides evidence of the scale "
            "and operational rigor behind that experience."
        )
        project = (
            "CampaignOS adds a current systems proof point: I designed the platform to standardize "
            "workflow governance, quality assurance, validation, and operational visibility."
        )
        close = (
            "I would welcome the chance to learn how the team is approaching YouTube Brand Auction, "
            "AI-powered campaign types, and seller activation, and to share how I could contribute."
        )
        return "\n\n".join(
            ["Hello,", opening, experience, project, close, "Best,\n\nTrisha Lynch"]
        )

    opening = (
        f"{role_reference} at {company} stood out because it brings {_job_focus(parsed_job)} "
        "together. The challenge of turning entertainment IP and franchise priorities into clear "
        "workflows, milestones, standards, and operating rhythms is work I find meaningful."
    )
    experience = (
        f"At {position_company}, I progressed to Group Director. "
        f"{_as_first_person(entertainment_scope)} I know how much operational clarity matters when creative, "
        "marketing, media, analytics, technology, and external partners need to move together."
    )
    project = ""
    if _campaignos_is_relevant(context) and campaignos:
        project = (
            "CampaignOS grew from that same instinct. I designed the AI-powered operations platform "
            "to standardize workflow governance, automate quality assurance, and give teams better "
            "consistency and visibility."
        )
    close = (
        "That mix of creative operations, product thinking, and scalable execution is where I do my "
        "best work. I would welcome the chance to learn more about the team's priorities and share "
        "how I could contribute."
    )
    parts = ["Hello,", opening, experience]
    if project:
        parts.append(project)
    parts.extend([close, "Best,\n\nTrisha Lynch"])
    return "\n\n".join(parts)


def generate_message(
    message_type: str,
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate and save a recruiter or hiring manager message."""
    normalized_type = message_type.replace("-", "_").lower()
    if normalized_type not in MESSAGE_TYPES:
        valid = ", ".join(message_type.replace("_", "-") for message_type in MESSAGE_TYPES)
        raise ApplicationMaterialError(f"Unknown message type '{message_type}'. Valid types: {valid}")

    context = load_generation_context(job_path, project_root)
    if normalized_type == "recruiter":
        return save_material(
            context,
            "Recruiter_Message",
            _recruiter_content(context),
            minimum_words=80,
            maximum_words=130,
        )

    return save_material(
        context,
        "Hiring_Manager_Message",
        _hiring_manager_content(context),
        minimum_words=120,
        maximum_words=180,
    )


def generate_recruiter_message(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    return generate_message("recruiter", job_path, project_root)


def generate_hiring_manager_message(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    return generate_message("hiring_manager", job_path, project_root)
