"""Generate grounded recruiter and hiring manager messages."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _entertainment_scope,
        _job_focus,
        _position,
        load_generation_context,
        save_material,
    )
    from .role_context import is_google_youtube_role
    from .human_positioning import validate_applicant_evidence
except ImportError:
    from generate_cover_letter import (
        ApplicationMaterialError,
        _as_first_person,
        _entertainment_scope,
        _job_focus,
        _position,
        load_generation_context,
        save_material,
    )
    from role_context import is_google_youtube_role
    from human_positioning import validate_applicant_evidence


PathInput = Union[str, Path]
MESSAGE_TYPES = ("recruiter", "hiring_manager")

DYNAMIC_MESSAGE_FOCUS = {
    "music_content_strategy": "music, audience connection, editorial voice, and content systems",
    "editorial_content_strategy": "editorial judgment, audience clarity, brand voice, and repeatable content systems",
    "transformation_advisory": "transformation thinking, stakeholder recommendations, operating models, and execution",
    "product_strategy_ops": "product and technology priorities, roadmaps, operating rhythms, and cross-functional decisions",
    "gtm_product_activation": "GTM activation, adoption, enablement, feedback loops, and measurable execution",
    "ai_operations_systems": "matrix operations, capacity visibility, dashboards, automation, and organizational clarity",
    "streaming_strategy": "streaming, content and franchise priorities, audience context, and executable strategy",
    "community_growth": "community understanding, audience trust, content, measurement, and sustainable growth",
    "business_operations": "ownership, capacity, decision cadence, and reliable cross-functional execution",
    "creative_marketing_ops": "creative and marketing priorities, workflow, quality, capacity, and delivery",
    "generic_senior_operator": "strategic clarity, stakeholder alignment, scalable systems, and dependable execution",
}

DYNAMIC_MESSAGE_PROOF = {
    "music_content_strategy": "At OMG23, I created and managed Multiverse, an internal culture publication that reached 400+ employees.",
    "editorial_content_strategy": "At OMG23, I created and managed Multiverse while building the contributor process that kept the publication moving.",
    "community_growth": "Multiverse and large-scale entertainment campaign work give me both audience and operating proof points.",
    "gtm_product_activation": "My professional background includes platform activation, measurement readiness, and large-advertiser execution.",
    "product_strategy_ops": "I have aligned business, analytics, and technology partners around workflows, milestones, and decisions.",
    "transformation_advisory": "My experience spans senior stakeholder alignment, workflow governance, and practical operating-model design.",
    "ai_operations_systems": "I have built governance, validation, quality standards, and clearer decision paths across complex teams.",
    "streaming_strategy": "I have led theatrical and streaming entertainment work and built systems that turn cross-functional priorities into execution.",
    "business_operations": "I have built workflow governance, execution standards, dashboards, and operational reporting across complex teams.",
    "creative_marketing_ops": "I have led large-scale entertainment marketing work and built creative workflows and quality standards.",
    "generic_senior_operator": "I have built workflow governance and execution standards around recurring operating problems.",
}


def _dynamic_message_copy(context: Dict[str, Any]) -> tuple[str, str]:
    effective = context.get("effective_voice_profile", context.get("profile", {}))
    role_family = str(effective.get("role_family") or "generic_senior_operator")
    return (
        DYNAMIC_MESSAGE_FOCUS.get(role_family, DYNAMIC_MESSAGE_FOCUS["generic_senior_operator"]),
        DYNAMIC_MESSAGE_PROOF.get(role_family, DYNAMIC_MESSAGE_PROOF["generic_senior_operator"]),
    )


def _profile_recruiter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    profile_key = context.get("profile_key", "default")
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    profile_copy = {
        "disney": (
            "product and technology strategy, executive operating rhythms, and enterprise entertainment",
            "My Disney Studios Theatrical and Disney Streaming/DSS work gives me practical context for the scale and coordination involved.",
        ),
        "paramount": (
            "marketing operations, creative capacity, workflow visibility, and high-volume entertainment execution",
            "I have led cross-functional entertainment work at scale and built clearer workflows, quality practices, and reporting rhythms.",
        ),
        "uta": (
            "transformation advisory, operating models, and strategy translated into execution",
            "My background spans media, marketing, advertising, and technology, with experience shaping clear recommendations for senior stakeholders and delivery teams.",
        ),
        "fieldai": (
            "matrix operations, organizational efficiency, capacity visibility, and AI workflow systems",
            "I have built governance, quality standards, and decision visibility across a fast-moving matrix.",
        ),
        "bandsintown": (
            "music, audience connection, editorial voice, and content systems",
            "Alongside entertainment marketing leadership, I created and managed Multiverse, an internal publication reaching 400+ employees.",
        ),
        "crunchyroll": (
            "streaming, fandom, franchise/IP, and enterprise strategy",
            "I have led theatrical and streaming entertainment work and built systems that turn cross-functional priorities into clearer execution.",
        ),
    }
    copy = profile_copy.get(profile_key)
    if copy is None:
        effective = context.get("effective_voice_profile", {})
        if effective.get("source") != "dynamic_inference" or effective.get("company_category") == "gaming_fandom":
            return ""
        copy = _dynamic_message_copy(context)
    focus, proof = copy
    message = (
        f"{role_reference} at {company} caught my attention because it connects {focus}. "
        f"I've spent much of my career solving similar operational challenges. {proof} I'm curious "
        "how the team is thinking about the problem and what would make the biggest difference first. "
        "If that perspective is relevant to the search, I'd be glad to share more context."
    )
    return "\n\n".join(["Hello,", message, "Best,\n\nTrisha Lynch"])


def _profile_hiring_manager_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    profile_key = context.get("profile_key", "default")
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    profile_copy = {
        "disney": (
            "aligning product, engineering, data, and business partners through useful OKRs and executive operating rhythms",
            "My work across Disney Studios Theatrical and Disney Streaming/DSS taught me how priorities move through a large entertainment ecosystem and where clear decisions matter most.",
            "My professional work adds a systems proof point through workflow governance, validation, and operational visibility.",
        ),
        "paramount": (
            "making marketing operations a practical connective layer between strategy, creative capacity, and delivery",
            "I built workflows and quality practices across creative, marketing, media, analytics, technology, and operations for high-volume entertainment campaigns.",
            "That work reflects how I use workflow systems and reporting to improve visibility without adding process for its own sake.",
        ),
        "uta": (
            "moving from a sound transformation hypothesis to an operating model and recommendation stakeholders can use",
            "My background across media, marketing, advertising, and technology lets me move between executive context, client-facing communication, and delivery detail.",
            "Workflow and governance work strengthened my approach to structured discovery, systems design, and carrying strategy through to implementation.",
        ),
        "fieldai": (
            "creating capacity visibility, decision paths, and shared operating cadences across a fast-moving matrix",
            "I designed governance, dashboards, quality systems, and execution standards across several functions in a fast-moving matrix.",
            "My governance and quality work provides evidence of validation frameworks, operational reporting, and clearer decision paths.",
        ),
        "bandsintown": (
            "writing with a distinct voice for artists, industry partners, and fans while building the content systems that keep quality consistent",
            "I have led entertainment marketing work and created Multiverse, an editorial publication centered on creativity, culture, music, innovation, and employee storytelling.",
            "Building the publication required editorial judgment, contributor guidance, and a repeatable content process that protected its human voice.",
        ),
        "crunchyroll": (
            "turning streaming, fandom, and franchise priorities into an enterprise strategy teams can execute",
            "My theatrical and streaming background spans Disney Studios Theatrical, Disney Streaming/DSS, and coordination across creative, media, technology, analytics, and operations.",
            "My workflow-governance work demonstrates how I translate recurring cross-functional friction into clearer validation and reporting practices.",
        ),
    }
    copy = profile_copy.get(profile_key)
    if copy is None:
        effective = context.get("effective_voice_profile", {})
        if effective.get("source") != "dynamic_inference" or effective.get("company_category") == "gaming_fandom":
            return ""
        focus, proof = _dynamic_message_copy(context)
        copy = (
            f"turning {focus} into an operating approach teams can understand and use",
            "I have learned to move between senior stakeholder context and delivery detail while making ownership and decisions easier to see.",
            proof,
        )
    challenge, experience, proof = copy
    opening = (
        f"{role_reference} at {company} caught my attention because it centers on {challenge}. "
        "It is the kind of problem where observation, clear judgment, and practical execution need to work together."
    )
    close = (
        "I'm curious how the team is defining success, where people currently lose time or context, "
        "and which outcome matters first. If comparing notes would be useful, I'd be glad to share "
        "what I have learned from solving similar problems."
    )
    return "\n\n".join(
        ["Hello,", opening, experience, proof, close, "Best,\n\nTrisha Lynch"]
    )


def _recruiter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"The {role} role" if role else "This opportunity"
    position = _position(career_data, "OMG23")
    position_company = str(position.get("company") or "OMG23 / OMD Entertainment").split(",")[0]
    entertainment_scope = _entertainment_scope(career_data)

    if is_google_youtube_role(parsed_job):
        message = (
            f"{role_reference} at {company} caught my attention because it connects "
            "YouTube product activation, GTM operations, and large advertiser execution. I have translated Google and YouTube platform "
            "capabilities into campaign execution, measurement readiness, and operational workflows "
            "across large entertainment advertisers. That work taught me how recurring activation "
            "needs become usable workflows. I'm curious which activation or "
            "feedback-loop challenge matters most to the team right now."
        )
        question = (
            "If that perspective is relevant to the search, I'd be glad to share more context."
        )
        return "\n\n".join(["Hello,", message, question, "Best,\n\nTrisha Lynch"])

    profile_content = _profile_recruiter_content(context)
    if profile_content:
        return profile_content

    message = (
        f"{role_reference} at {company} caught my attention because it connects "
        f"{_job_focus(parsed_job)} around entertainment IP. At {position_company}, "
        f"{_as_first_person(entertainment_scope)} I built workflows, quality practices, and operating "
        "standards that helped cross-functional campaign teams coordinate complex work."
    )
    question = (
        "I'm curious which part of that operating challenge matters most to the team. If my "
        "perspective is relevant to the search, I'd be glad to share more context."
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

    entertainment_scope = _entertainment_scope(career_data)

    if is_google_youtube_role(parsed_job):
        opening = (
            f"{role_reference} at {company} caught my attention because it brings YouTube product activation, "
            "GTM operations, seller enablement, and large advertiser execution together. Translating "
            "platform priorities into clear activation strategies, feedback loops, and measurable "
            "execution is work I find meaningful."
        )
        experience = (
            "Across large entertainment advertisers, I have translated Google and YouTube platform "
            "capabilities into campaign operations, measurement readiness, and brand activation while "
            "aligning marketing, media, analytics, technology, and senior stakeholders. "
            "Disney Studios Theatrical and Disney Streaming/DSS work provides evidence of the scale "
            "and operational rigor behind that experience."
        )
        project = (
            "At OMG23, I built workflow governance, quality practices, and measurement-readiness "
            "routines that gave teams clearer operational visibility."
        )
        close = (
            "I'm curious where the team sees the hardest adoption or feedback-loop problem around "
            "YouTube Brand Auction, AI-powered campaign types, and seller activation. If useful, "
            "I'd be glad to compare notes on what makes those operating systems work in practice."
        )
        return "\n\n".join(
            ["Hello,", opening, experience, project, close, "Best,\n\nTrisha Lynch"]
        )

    profile_content = _profile_hiring_manager_content(context)
    if profile_content:
        return profile_content

    opening = (
        f"{role_reference} at {company} caught my attention because it brings {_job_focus(parsed_job)} "
        "together. The challenge of turning entertainment IP and franchise priorities into clear "
        "workflows, milestones, standards, and operating rhythms is work I find meaningful."
    )
    experience = (
        f"At {position_company}, {_as_first_person(entertainment_scope)} I built workflows and quality "
        "practices around that work, and learned how much operational clarity matters when creative, "
        "marketing, media, analytics, technology, and external partners need to move together."
    )
    project = (
        "I also introduced workflow governance and execution standards that improved consistency "
        "and visibility across marketing, technology, analytics, and creative teams."
    )
    close = (
        "I'm curious where the team loses the most time or context and what matters first. If useful, "
        "I'd be glad to compare notes on what has worked in similar environments."
    )
    parts = ["Hello,", opening, experience]
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
        content = _recruiter_content(context)
        validate_applicant_evidence(content, "recruiter message")
        return save_material(
            context,
            "Recruiter_Message",
            content,
            minimum_words=80,
            maximum_words=130,
        )
    content = _hiring_manager_content(context)
    validate_applicant_evidence(content, "hiring manager message")
    return save_material(
        context,
        "Hiring_Manager_Message",
        content,
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
