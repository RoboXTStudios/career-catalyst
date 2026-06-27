"""Generate a short, grounded note for application portals."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )
except ImportError:
    from generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )


PathInput = Union[str, Path]


def _application_note_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    return (
        f"{role_reference} at {company} caught my attention because it connects creative operations, "
        "product development, and entertainment IP. At "
        f"{position_company}, my primary work centered on Disney Studios Theatrical and Disney "
        "Streaming/DSS, supporting theatrical and streaming film campaigns across 20th Century "
        "Studios, Disney+, and franchise/IP priorities. I led cross-functional execution through "
        "workflows, milestones, QA, standards, and partner coordination, and built CampaignOS to "
        "turn recurring operational challenges into scalable systems."
    )


def generate_application_note(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate and save a short application portal note."""
    context = load_generation_context(job_path, project_root)
    return save_material(
        context,
        "Application_Note",
        _application_note_content(context),
        minimum_words=60,
        maximum_words=100,
    )
