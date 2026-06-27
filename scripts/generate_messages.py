"""Generate grounded recruiter and hiring manager messages."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _achievement,
        _campaignos_is_relevant,
        _job_focus,
        _position,
        _project,
        load_generation_context,
        save_material,
    )
except ImportError:
    from generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _achievement,
        _campaignos_is_relevant,
        _job_focus,
        _position,
        _project,
        load_generation_context,
        save_material,
    )


PathInput = Union[str, Path]
MESSAGE_TYPES = ("recruiter", "hiring_manager")


def _recruiter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "the open role"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    message = (
        f"I'm reaching out about {company}'s {role} role. It caught my attention because it brings "
        f"{_job_focus(parsed_job)} into a global entertainment setting. I have spent more than 20 "
        "years helping creative and marketing organizations turn complex work into repeatable "
        f"systems. At {position_company}, that included progressing to Group Director, leading "
        "cross-functional teams of 60+, and helping operationalize the Disney+ launch."
    )
    question = (
        "If you're the right person to speak with, I would be glad to share more. If not, would "
        "you mind pointing me in the right direction?"
    )
    return "\n\n".join(["Hello,", message, question, "Best,\n\nTrisha Lynch"])


def _hiring_manager_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "the open role"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    disney_plus = _achievement(career_data, "disney_plus_launch_support")
    workflow = _achievement(career_data, "workflow_governance")
    campaignos = _project(career_data, "CampaignOS")

    opening = (
        f"{company}'s {role} role stood out to me because it sits where strategy, operations, and "
        "creative execution meet. The challenge of turning company priorities into clear plans and "
        "operating rhythms is work I find meaningful."
    )
    experience = (
        f"At {position_company}, I progressed to Group Director and led cross-functional teams of "
        "60+ across marketing, creative, analytics, and ad operations. "
        f"{_as_first_person(disney_plus)} {_as_first_person(workflow)} I know how much operational "
        "clarity matters when creative teams are moving quickly and many functions need to move together."
    )
    project = ""
    if _campaignos_is_relevant(context) and campaignos:
        project = (
            "CampaignOS grew from that same instinct. I designed the AI-powered operations platform "
            "to standardize workflow governance, automate quality assurance, and give teams better "
            "consistency and visibility."
        )
    close = (
        "That mix of strategy, operations, and creative execution is where I do my best work. I "
        "would welcome the chance to learn more about the team's priorities and share how I could contribute."
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
