"""Generate concise, role-specific interview preparation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .employer_identity import normalize_applicant_employer_names
    from .filename_utils import build_upload_filename
    from .generate_cover_letter import load_generation_context
    from .human_positioning import personal_project_violations, validate_applicant_evidence
    from .package_context import validate_material_context
    from .role_lens import enforce_role_lens_quality
except ImportError:
    from employer_identity import normalize_applicant_employer_names
    from filename_utils import build_upload_filename
    from generate_cover_letter import load_generation_context
    from human_positioning import personal_project_violations, validate_applicant_evidence
    from package_context import validate_material_context
    from role_lens import enforce_role_lens_quality


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
    proof_points = [
        str(value)
        for value in intelligence.get("proof_points_to_emphasize", [])
        if not personal_project_violations(str(value))
    ][:4]
    people_operations = context.get("role_lens", {}).get("primary") == "people_operations"
    themes = (
        [
            "team effectiveness and leadership",
            "cross-functional partnership",
            "change adoption",
            "ownership and communication clarity",
            "usable systems and standards",
            "transparent transferable fit",
        ]
        if people_operations
        else keywords
        or ["cross-functional leadership", "operating clarity", "measurable execution"]
    )
    unsupported = [
        item
        for item in context.get("requirement_map", [])
        if item.get("strength") == "Unsupported"
    ]
    questions = (
        [
            "Where do managers and teams experience the most recurring friction in current People programs or processes?",
            "Which responsibilities require deep HR subject-matter ownership, and where would strong operating leadership add the most value?",
            "How does feedback from managers, employees, and People Operations specialists shape program improvements today?",
            "What would meaningful progress look like in the first 90 days for both execution and team experience?",
        ]
        if people_operations
        else [
            "What would meaningful progress look like in the first 90 days?",
            "Where does work lose the most time, context, or ownership today?",
            "Which relationships will matter most for this person to build early?",
            "How does the team balance immediate delivery with longer-term operational improvement?",
        ]
    )
    story_prompts = (
        [
            "A time you listened to several teams and found the recurring friction behind a process problem.",
            "A time clearer ownership or communication improved how people worked together.",
            "A change that teams adopted because the workflow and expectations were practical.",
            "A time you led a cross-functional team through competing priorities without adding unnecessary bureaucracy.",
        ]
        if people_operations
        else [
            "A time you turned an unclear cross-functional problem into a practical operating plan.",
            "A time you improved a process without losing the trust or judgment of the people doing the work.",
            "A time you used data, workflow design, or reporting to improve visibility and execution.",
            "A decision where you balanced speed, quality, stakeholder needs, and limited capacity.",
        ]
    )
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
            *(
                f"- {value}"
                for value in (
                    proof_points
                    or [
                        "cross-functional leadership across creative, media, analytics, and technology",
                        "workflow governance and quality assurance",
                        "Disney theatrical and streaming campaign operations",
                    ]
                )
            ),
            "",
            "### Story Prompts",
            "",
            *(f"- {value}" for value in story_prompts),
            "",
            "### Requirement Gaps",
            "",
            *(
                f"- {item['normalized_concept']}: do not claim direct ownership; discuss the "
                "operations background as transferable only if asked."
                for item in unsupported
            ),
            "",
            "### Questions to Ask",
            "",
            *(f"- {value}" for value in questions),
            "",
            "### Voice Reminder",
            "",
            "Be specific and conversational. Lead with the situation and decision, then the operating change and measurable result. Do not overstate company familiarity.",
            "",
        )
    )
    content = normalize_applicant_employer_names(content)
    content, quality = enforce_role_lens_quality(
        content, context.get("role_lens", {}), material_type="interview_prep"
    )
    if not quality["valid"]:
        raise ValueError(
            f"Interview prep does not match role lens: {quality['violations'][0]['code']}"
        )
    validate_applicant_evidence(content, "interview prep")
    validate_material_context(content, parsed, "Interview_Prep")
    filename = build_upload_filename(
        "Trisha Lynch", role, company, "Interview Prep", "txt"
    )
    root = Path(project_root) if project_root is not None else Path.cwd()
    output_path = root / "exports" / "strategy_packs" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return {
        "job_title": role,
        "company": company,
        "output_path": str(output_path),
        "role_lens": context.get("role_lens", {}),
        "requirement_map": context.get("requirement_map", []),
        "role_lens_quality": quality,
    }
