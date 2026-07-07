"""Generate concise, role-specific interview preparation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .filename_utils import build_upload_filename
    from .generate_cover_letter import load_generation_context
    from .package_context import validate_material_context
except ImportError:
    from filename_utils import build_upload_filename
    from generate_cover_letter import load_generation_context
    from package_context import validate_material_context


PathInput = Union[str, Path]


def generate_interview_prep(
    job_path: PathInput, project_root: Optional[PathInput] = None
) -> Dict[str, Any]:
    """Create a grounded interview-prep file from dynamic role intelligence."""
    context = load_generation_context(job_path, project_root)
    parsed = context["parsed_job"]
    intelligence = context.get("effective_voice_profile", {})
    company = str(parsed.get("company") or "the company")
    role = str(parsed.get("job_title") or "the role")
    keywords = [str(value) for value in parsed.get("keywords", [])[:6]]
    proof_points = [str(value) for value in intelligence.get("proof_points_to_emphasize", [])[:4]]
    themes = keywords or ["cross-functional leadership", "operating clarity", "measurable execution"]
    content = "\n".join(
        (
            "# Interview Prep",
            "",
            f"## {role} at {company}",
            "",
            "### Likely Themes",
            "",
            *(f"- {value}" for value in themes),
            "",
            "### Proof Points to Prepare",
            "",
            *(f"- {value}" for value in (proof_points or ["cross-functional leadership", "workflow governance", "CampaignOS"])),
            "",
            "### Story Prompts",
            "",
            "- A time you turned an unclear cross-functional problem into a practical operating plan.",
            "- A time you improved a process without losing the trust or judgment of the people doing the work.",
            "- A time you used data, automation, or an AI-enabled workflow to improve visibility and execution.",
            "- A decision where you balanced speed, quality, stakeholder needs, and limited capacity.",
            "",
            "### Questions to Ask",
            "",
            "- What would meaningful progress look like in the first 90 days?",
            "- Where does work lose the most time, context, or ownership today?",
            "- Which relationships will matter most for this person to build early?",
            "- How does the team balance immediate delivery with longer-term operational improvement?",
            "",
            "### Voice Reminder",
            "",
            "Be specific and conversational. Lead with the situation and decision, then the operating change and measurable result. Do not overstate company familiarity.",
            "",
        )
    )
    validate_material_context(content, parsed, "Interview_Prep")
    filename = build_upload_filename(
        "Trisha Lynch", role, company, "Interview Prep", "md"
    )
    root = Path(project_root) if project_root is not None else Path.cwd()
    output_path = root / "exports" / "strategy_packs" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return {
        "job_title": role,
        "company": company,
        "output_path": str(output_path),
    }
