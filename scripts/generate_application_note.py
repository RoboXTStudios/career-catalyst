"""Generate a short, grounded note for application portals."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .employer_identity import OMG23_DISPLAY_NAME
    from .generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )
    from .role_context import is_google_youtube_role
except ImportError:
    from employer_identity import OMG23_DISPLAY_NAME
    from generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )
    from role_context import is_google_youtube_role


PathInput = Union[str, Path]

DYNAMIC_NOTE_FOCUS = {
    "people_operations": "team effectiveness, ownership clarity, communication, change adoption, and practical systems",
    "music_content_strategy": "music, audience understanding, editorial voice, and content systems",
    "editorial_content_strategy": "editorial judgment, audience clarity, voice, and dependable content operations",
    "transformation_advisory": "transformation, stakeholder recommendations, operating models, and implementation",
    "product_strategy_ops": "product and technology priorities, roadmaps, OKRs, and operating rhythms",
    "gtm_product_activation": "GTM activation, adoption, enablement, feedback loops, and measurement",
    "ai_operations_systems": "matrix operations, capacity visibility, dashboards, automation, and governance",
    "streaming_strategy": "streaming, content and franchise priorities, audience context, and execution",
    "community_growth": "community trust, audience growth, content, measurement, and repeatable programs",
    "business_operations": "ownership, capacity planning, decision cadence, and cross-functional delivery",
    "creative_marketing_ops": "creative and marketing priorities, workflow, quality, capacity, and delivery",
    "generic_senior_operator": "strategic clarity, stakeholder alignment, scalable systems, and execution",
}


def _profile_application_note(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    profile_key = context.get("profile_key", "default")
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "This opportunity"
    if context.get("role_lens", {}).get("primary") == "people_operations":
        return (
            f"The {role} role at {company} stood out because it focuses on how people, process, "
            "communication, and business priorities work together. At "
            f"{OMG23_DISPLAY_NAME}, I led cross-functional teams and introduced clearer workflows, "
            "responsibilities, standards, and communication practices. I would bring that experience to improving "
            "how teams adopt practical systems and work together."
        )
    notes = {
        "disney": (
            f"The {role} role at {company} caught my attention because it connects product and "
            "technology strategy, OKRs, and executive operating rhythms within a large entertainment "
            "ecosystem. My Disney Studios Theatrical and Disney Streaming/DSS experience gives me "
            "practical context for that scale. I have aligned creative, marketing, analytics, technology, "
            "and operations partners while improving workflow governance, validation, and operational visibility."
        ),
        "paramount": (
            f"The {role} role at {company} stood out because marketing operations is the connective "
            "layer between strategy, creative capacity, and delivery. I have led teams of 60+ across "
            "entertainment marketing functions and built workflows, standards, quality practices, and "
            "reporting rhythms that turned recurring delivery friction into clearer decisions."
        ),
        "uta": (
            f"The {role} role at {company} stood out because it combines transformation advisory, "
            "operating models, stakeholder management, and strategy into execution. My background spans "
            "media, marketing, advertising, and technology, with experience translating senior stakeholder "
            "priorities into practical recommendations and delivery systems. Workflow-governance work "
            "developed my structured approach from discovery through implementation."
        ),
        "fieldai": (
            f"The {role} role at {company} caught my attention because it centers on matrix operations, "
            "organizational efficiency, capacity visibility, and operating cadences. I have led teams of "
            "60+ and built governance, quality systems, and decision visibility across several functions "
            "without adding unnecessary process."
        ),
        "bandsintown": (
            f"The {role} role at {company} stood out because it connects music, audience understanding, "
            "editorial voice, and content systems. Alongside leading entertainment marketing work, I created "
            "and managed Multiverse, an internal publication centered on creativity, culture, music, and "
            "innovation. Building its contributor process required both editorial judgment and operational discipline."
        ),
        "crunchyroll": (
            f"The {role} role at {company} caught my attention because it connects streaming, fandom, "
            "franchise/IP, and enterprise strategy. I have led theatrical and streaming entertainment "
            "work across creative, marketing, media, analytics, technology, and operations, turning "
            "cross-functional priorities into clearer governance, validation, and reporting."
        ),
    }
    return notes.get(profile_key, "")


def _application_note_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]

    if is_google_youtube_role(parsed_job):
        return (
            "This Google opportunity caught my attention because it connects YouTube product "
            "activation, GTM operations, and large advertiser execution. I have translated Google "
            "and YouTube platform capabilities into campaign execution, "
            "measurement readiness, and operational workflows across large entertainment advertisers. "
            "That foundation aligns with Brand Auction activation, seller enablement, senior stakeholder "
            "alignment, and product feedback loops. I'm curious which activation challenge the team "
            "most wants this role to clarify first."
        )

    profile_note = _profile_application_note(context)
    if profile_note:
        return (
            f"{profile_note} I'm curious where the team most needs clearer ownership, better "
            "visibility, or a more dependable operating rhythm."
        )

    effective = context.get("effective_voice_profile", {})
    if (
        effective.get("source") == "dynamic_inference"
        and effective.get("company_category") != "gaming_fandom"
    ):
        role_family = str(effective.get("role_family") or "generic_senior_operator")
        focus = DYNAMIC_NOTE_FOCUS.get(
            role_family, DYNAMIC_NOTE_FOCUS["generic_senior_operator"]
        )
        if role_family in {
            "music_content_strategy",
            "editorial_content_strategy",
            "community_growth",
        }:
            proof = (
                "At OMG23, I created and managed Multiverse, an internal publication reaching 400+ "
                "employees, alongside large-scale entertainment marketing work."
            )
        else:
            proof = (
                "I have led cross-functional teams of 60+ and built workflow governance, execution "
                "standards, quality practices, and reporting rhythms at scale."
            )
        return (
            f"The {role} role at {company} caught my attention because it centers on {focus}. "
            f"{proof} I would bring calm judgment, practical systems thinking, and a grounded "
            "approach based on the role's stated priorities rather than assumptions about the company."
        )

    return (
        f"{role_reference} at {company} caught my attention because it connects creative operations, "
        "product development, and entertainment IP. At "
        f"{position_company}, my primary work centered on Disney Studios Theatrical and Disney "
        "Streaming/DSS, supporting theatrical and streaming film campaigns across 20th Century "
        "Studios, Disney+, and franchise/IP priorities. I led cross-functional execution through "
        "workflows, milestones, QA, standards, and partner coordination."
    )


def generate_application_note(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a short application portal note."""
    context = load_generation_context(job_path, project_root, package_context)
    return save_material(
        context,
        "Application_Note",
        _application_note_content(context),
        minimum_words=60,
        maximum_words=100,
    )
