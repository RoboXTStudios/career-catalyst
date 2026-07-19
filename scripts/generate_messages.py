"""Generate grounded recruiter and hiring manager messages."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .employer_identity import OMG23_DISPLAY_NAME
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
    from .public_advocacy import rewrite_public_advocacy, validate_public_advocacy
except ImportError:
    from employer_identity import OMG23_DISPLAY_NAME
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
    from public_advocacy import rewrite_public_advocacy, validate_public_advocacy


PathInput = Union[str, Path]
MESSAGE_TYPES = ("recruiter", "hiring_manager")

DYNAMIC_MESSAGE_FOCUS = {
    "people_operations": "how teams communicate, understand ownership, adopt change, and use practical systems",
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
    "people_operations": "I have led cross-functional teams and introduced clearer workflows, responsibilities, standards, and communication practices people could use in daily work.",
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
    interpreted_archetype = str(
        (context.get("role_interpretation") or {}).get("primary_archetype") or ""
    )
    selected_profile_ids = {
        str(item.get("id")) for item in context.get("selected_profile_evidence") or []
    }
    if "career_catalyst_ai_product" in selected_profile_ids:
        message = (
            f"{role_reference} at {company} stood out because it connects AI product judgment with usable workflows and responsible delivery. "
            "I am the product owner and domain lead for a functioning AI-enabled career intelligence product, where I defined requirements, designed human-in-the-loop workflows, evaluated outputs, directed Codex implementation, and led UAT. "
            "That work gives me hands-on experience in AI workflow, prompt and context design, evaluation, provenance, and safety controls. I would welcome the opportunity to discuss how that product approach could support the team."
        )
        return "\n\n".join(["Hello,", message, "Best,\n\nTrisha Lynch"])
    if interpreted_archetype in {
        "Technical Solutions / Solutions Consulting",
        "Advertising Technology / Ad Operations",
        "Implementation / Onboarding",
        "Sales Engineering",
    }:
        message = (
            f"{role_reference} at {company} stood out because it connects technical platform execution, customer or advertiser problem-solving, and product partnership. "
            "My direct advertising-technology experience includes Google and YouTube activation, CM360 and DV360 implementation, conversion tracking, measurement readiness, QA, and technical troubleshooting. "
            "I have also supported server-to-server conversion API implementation from the business and campaign-operations side, partnering across technical and business teams to improve advertiser delivery. I would welcome the opportunity to contribute that experience."
        )
        return "\n\n".join(["Hello,", message, "Best,\n\nTrisha Lynch"])
    if context.get("role_lens", {}).get("primary") == "people_operations":
        message = (
            f"{role_reference} at {company} stood out because it focuses on how people, process, "
            "communication, and business priorities come together. At "
            f"{OMG23_DISPLAY_NAME}, I led cross-functional teams and built clearer ways of working "
            "around ownership, communication, standards, and change. The value I would bring is a "
            "practical understanding of how teams adopt systems and work together more effectively. "
            "I would welcome the opportunity to contribute that practical, people-centered perspective across a complex organization."
        )
        return "\n\n".join(["Hello,", message, "Best,\n\nTrisha Lynch"])
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
    interpreted_archetype = str(
        (context.get("role_interpretation") or {}).get("primary_archetype") or ""
    )
    selected_profile_ids = {
        str(item.get("id")) for item in context.get("selected_profile_evidence") or []
    }
    if "career_catalyst_ai_product" in selected_profile_ids:
        opening = (
            f"What interests me about {role_reference.lower()} at {company} is the need to turn AI capability into a product people can understand, review, and trust."
        )
        experience = (
            "I am the product owner and domain lead for a functioning AI-enabled career intelligence product. I defined its product behavior and acceptance criteria, designed the reasoning and human-review workflow, and directed Codex implementation while testing the product against real jobs and failure modes. The system connects interpretation, persistent evidence, scoring, package generation, provenance, review, and user confirmation controls."
        )
        proof = (
            "My hands-on AI product ownership includes workflow and requirements design, prompt and context design, evaluation, responsible-AI safeguards, UAT, and iterative delivery. I use those disciplines together to turn product intent into reliable behavior and clear user controls."
        )
        close = (
            "I am curious which product decisions, evaluation challenges, and adoption risks matter most in the first six months, and how the team currently turns user feedback into reliable product behavior."
        )
        return "\n\n".join(["Hello,", opening, experience, proof, close, "Best,\n\nTrisha Lynch"])
    if interpreted_archetype in {
        "Technical Solutions / Solutions Consulting",
        "Advertising Technology / Ad Operations",
        "Implementation / Onboarding",
        "Sales Engineering",
    }:
        opening = (
            f"What interests me about {role_reference.lower()} at {company} is the need to make technical products reliable and usable for customers or advertisers while connecting sales, product, and engineering."
        )
        experience = (
            "At OMG23 / OMD Entertainment, I led Disney theatrical and streaming campaign operations across media, analytics, technology, creative, and operations. My direct platform work included CM360 and DV360 implementation, trafficking, conversion tracking, measurement validation, launch readiness, QA, and technical troubleshooting for large entertainment advertisers."
        )
        proof = (
            "I also supported server-to-server conversion API implementation from the business and campaign-operations side, clarifying requirements, coordinating technical partners, validating launch readiness, and resolving measurement issues. That work strengthened my ability to connect advertiser needs with reliable technical execution."
        )
        close = (
            "I am curious how the team divides hands-on implementation, advertiser consultation, escalation ownership, and people leadership, and which of those outcomes matters most in the first six months."
        )
        return "\n\n".join(["Hello,", opening, experience, proof, close, "Best,\n\nTrisha Lynch"])
    if context.get("role_lens", {}).get("primary") == "people_operations":
        opening = (
            f"What interests me about {role_reference.lower()} at {company} is the work of turning "
            "business priorities into programs and systems that teams can actually use. The posting's "
            "focus on cross-functional partnership, clear reporting, continuous improvement, and team "
            "effectiveness points to a practical challenge: improving consistency without losing the "
            "human context behind how work gets done."
        )
        experience = (
            f"At {OMG23_DISPLAY_NAME}, I led cross-functional teams and introduced clearer workflows, "
            "responsibilities, standards, and communication practices across several functions. My "
            "experience has consistently required listening to teams, identifying recurring friction, and helping people adopt new "
            "ways of working without adding unnecessary bureaucracy."
        )
        close = (
            f"I would welcome the opportunity to help {company} reduce avoidable friction for managers and teams, "
            "strengthen ownership and communication, and build People programs that employees can trust and sustain."
        )
        return "\n\n".join(
            ["Hello,", opening, experience, close, "Best,\n\nTrisha Lynch"]
        )
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


def _raw_recruiter_content(context: Dict[str, Any]) -> str:
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


def _recruiter_content(context: Dict[str, Any]) -> str:
    parsed = context.get("parsed_job") or {}
    content, _review = rewrite_public_advocacy(
        _raw_recruiter_content(context),
        company=str(parsed.get("company") or "the organization"),
        role=str(parsed.get("job_title") or "the role"),
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    validate_public_advocacy(
        content,
        "recruiter message",
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    return content


def _raw_hiring_manager_content(context: Dict[str, Any]) -> str:
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


def _hiring_manager_content(context: Dict[str, Any]) -> str:
    parsed = context.get("parsed_job") or {}
    content, _review = rewrite_public_advocacy(
        _raw_hiring_manager_content(context),
        company=str(parsed.get("company") or "the organization"),
        role=str(parsed.get("job_title") or "the role"),
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    validate_public_advocacy(
        content,
        "hiring manager message",
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    return content


def generate_message(
    message_type: str,
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a recruiter or hiring manager message."""
    normalized_type = message_type.replace("-", "_").lower()
    if normalized_type not in MESSAGE_TYPES:
        valid = ", ".join(message_type.replace("_", "-") for message_type in MESSAGE_TYPES)
        raise ApplicationMaterialError(f"Unknown message type '{message_type}'. Valid types: {valid}")

    context = load_generation_context(job_path, project_root, package_context)
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
