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
    role = parsed_job.get("job_title") or "the open role"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    return (
        f"What caught my attention about {company}'s {role} role is the intersection of strategy, "
        "cross-functional operations, and entertainment scale. I have spent much of my career helping creative and marketing "
        f"teams turn complex work into clear, repeatable systems. At {position_company}, that "
        "included leading cross-functional operations and helping operationalize the Disney+ launch. "
        "I would welcome the chance to bring that same blend of strategic thinking, operational "
        "clarity, and AI systems work to a team building across streaming and fandom."
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
