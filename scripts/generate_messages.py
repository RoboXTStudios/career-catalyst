"""Generate grounded recruiter and hiring manager messages."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .career_claims import leadership_claim, public_omg23_name
    from .evidence_tailoring import candidate_project_reference_violations
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
    from career_claims import leadership_claim, public_omg23_name
    from evidence_tailoring import candidate_project_reference_violations
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

DYNAMIC_MESSAGE_FOCUS = {
    "music_content_strategy": "music, audience connection, editorial voice, and content systems",
    "editorial_content_strategy": "editorial judgment, audience clarity, brand voice, and repeatable content systems",
    "transformation_advisory": "transformation thinking, stakeholder recommendations, operating models, and execution",
    "product_marketing": "audience insight, product positioning, messaging, go-to-market planning, launch readiness, and adoption",
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
    "music_content_strategy": "I created Multiverse and develop creative publishing systems through RoboXT Studios alongside entertainment marketing leadership.",
    "editorial_content_strategy": "I created Multiverse, build through RoboXT Studios, and have developed the operating systems that keep high-volume work moving.",
    "community_growth": "Multiverse, RoboXT Studios, and large-scale audience campaign work provide both community and operating proof points.",
    "product_marketing": "My background includes entertainment marketing delivery, launch readiness, audience communications, platform adoption, and cross-functional enablement.",
    "gtm_product_activation": "My background includes platform activation, measurement readiness, large advertiser execution, and CampaignOS product thinking.",
    "product_strategy_ops": "I have aligned business, analytics, and technology partners and built CampaignOS as a current product and systems proof point.",
    "transformation_advisory": "My experience spans senior stakeholder alignment, operating-model design, and CampaignOS as strategy translated into a working system.",
    "ai_operations_systems": "I {leadership} and built CampaignOS around automation, governance, validation, dashboards, and better decisions.",
    "streaming_strategy": "I have led theatrical and streaming entertainment work and built systems that turn cross-functional priorities into execution.",
    "business_operations": "I {leadership} and built workflow governance, execution standards, dashboards, and operational reporting.",
    "creative_marketing_ops": "I have led large-scale entertainment marketing work and built creative workflows, quality standards, and CampaignOS.",
    "generic_senior_operator": "I {leadership} and built workflow governance, execution standards, and CampaignOS systems at scale.",
}


def _dynamic_message_copy(context: Dict[str, Any]) -> tuple[str, str]:
    effective = context.get("effective_voice_profile", context.get("profile", {}))
    role_family = str(effective.get("role_family") or "generic_senior_operator")
    proof = DYNAMIC_MESSAGE_PROOF.get(
        role_family, DYNAMIC_MESSAGE_PROOF["generic_senior_operator"]
    ).format(leadership=leadership_claim(context["career_data"]))
    selected_ids = {
        str(project.get("id") or project.get("title") or project.get("name") or "").lower()
        for project in context.get("associated_evidence_projects") or []
    }
    if "campaignos" in proof.lower() and not any("campaignos" in value for value in selected_ids):
        proof = (
            f"I {leadership_claim(context['career_data'])} and built workflow governance, "
            "execution standards, dashboards, and operational reporting."
        )
    return (
        DYNAMIC_MESSAGE_FOCUS.get(role_family, DYNAMIC_MESSAGE_FOCUS["generic_senior_operator"]),
        proof,
    )


def _authorized_project_copy(
    context: Dict[str, Any], content: str, fallback: str, artifact_type: str
) -> str:
    """Keep profile copy grounded in the manually selected Evidence pool."""
    if context.get("associated_evidence_projects") and candidate_project_reference_violations(
        content, context, artifact_type
    ):
        return fallback
    return content


def _profile_recruiter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    profile_key = context.get("profile_key", "default")
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"the {role} role" if role else "this opportunity"
    profile_copy = {
        "disney": (
            "product and technology strategy, executive operating rhythms, and enterprise entertainment",
            "My Disney Studios Theatrical and Disney Streaming/DSS experience gives me context for the scale, while CampaignOS reflects my current systems thinking.",
        ),
        "paramount": (
            "marketing operations, creative capacity, workflow visibility, and high-volume entertainment execution",
            "I have led cross-functional entertainment work at scale and built AI-enabled workflow and reporting systems through CampaignOS.",
        ),
        "uta": (
            "transformation advisory, operating models, and strategy translated into execution",
            "My background spans media, marketing, advertising, and technology, with experience shaping clear recommendations for senior stakeholders and delivery teams.",
        ),
        "fieldai": (
            "matrix operations, organizational efficiency, capacity visibility, and AI workflow systems",
            f"I {leadership_claim(context['career_data'])} and built CampaignOS around automation, governance, dashboards, and better operational decisions.",
        ),
        "bandsintown": (
            "music, audience connection, editorial voice, and content systems",
            "Alongside entertainment marketing leadership, I created Multiverse and now develop creative publishing systems through RoboXT Studios, giving me both editorial and operational proof points.",
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
    proof = _authorized_project_copy(
        context,
        proof,
        f"I {leadership_claim(context['career_data'])} and built practical governance, "
        "workflow, quality, and reporting systems for complex cross-functional work.",
        "recruiter_message",
    )
    message = (
        f"I'm reaching out about {role_reference} at {company}. It stood out because it connects "
        f"{focus}. {proof} That combination of clear context and disciplined execution is where I "
        "do my best work. If you're the right person to speak with, I would be glad to share more. "
        "If not, would you mind pointing me in the right direction?"
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
            "CampaignOS adds a current product and systems proof point through workflow governance, validation, and operational visibility.",
        ),
        "paramount": (
            "making marketing operations a practical connective layer between strategy, creative capacity, and delivery",
            f"I {leadership_claim(context['career_data'])} while directing high-volume entertainment campaign operations.",
            "CampaignOS reflects how I use AI enablement, dashboards, and workflow systems to improve visibility without adding process for its own sake.",
        ),
        "uta": (
            "moving from a sound transformation hypothesis to an operating model and recommendation stakeholders can use",
            "My background across media, marketing, advertising, and technology lets me move between executive context, client-facing communication, and delivery detail.",
            "Building CampaignOS strengthened my approach to structured discovery, systems design, and carrying strategy through to implementation.",
        ),
        "fieldai": (
            "creating capacity visibility, decision paths, and shared operating cadences across a fast-moving matrix",
            f"I {leadership_claim(context['career_data'])} and designed governance, dashboards, quality systems, and execution standards across several functions.",
            "CampaignOS is direct evidence of my AI-forward systems work, including automation, validation frameworks, and operational reporting.",
        ),
        "bandsintown": (
            "writing with a distinct voice for artists, industry partners, and fans while building the content systems that keep quality consistent",
            "I have led entertainment marketing work and created Multiverse, an editorial publication centered on creativity, culture, music, innovation, and employee storytelling.",
            "RoboXT Studios gives me an independent place to develop creative, photography, editorial, and publishing systems with a distinct human voice.",
        ),
        "crunchyroll": (
            "turning streaming, fandom, and franchise priorities into an enterprise strategy teams can execute",
            "My theatrical and streaming background spans Disney Studios Theatrical, Disney Streaming/DSS, and coordination across creative, media, technology, analytics, and operations.",
            "CampaignOS demonstrates how I translate recurring cross-functional friction into clearer governance, validation, and reporting systems.",
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
            f"I {leadership_claim(context['career_data'])} and learned to move between senior stakeholder context and delivery detail.",
            proof,
        )
    challenge, experience, proof = copy
    experience = _authorized_project_copy(
        context,
        experience,
        f"I {leadership_claim(context['career_data'])} while aligning senior stakeholders "
        "with complex delivery work.",
        "hiring_manager_message",
    )
    proof = _authorized_project_copy(
        context,
        proof,
        "I have built practical governance, workflow, quality, and reporting systems that make "
        "ownership, dependencies, and decisions easier to see.",
        "hiring_manager_message",
    )
    opening = (
        f"{role_reference} at {company} stood out because it centers on {challenge}. "
        "That is the kind of problem where clear judgment and practical execution need to work together."
    )
    close = (
        "I would welcome the chance to learn how the team is defining success and share how my "
        "experience could contribute. That conversation would also help me understand where the "
        "team sees the greatest friction and which outcomes matter first."
    )
    return "\n\n".join(
        ["Hello,", opening, experience, proof, close, "Best,\n\nTrisha Lynch"]
    )


def _recruiter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    role_reference = f"the {role} role" if role else "this opportunity"
    position = _position(career_data, "OMG23")
    position_company = public_omg23_name(career_data)
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

    profile_content = _profile_recruiter_content(context)
    if profile_content:
        return profile_content

    message = (
        f"I'm reaching out about {role_reference} at {company}. It stands out because it "
        f"connects {_job_focus(parsed_job)} around entertainment IP. At {position_company}, "
        f"{_as_first_person(entertainment_scope)} I {leadership_claim(career_data)} and built "
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
    position_company = public_omg23_name(career_data)

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

    profile_content = _profile_hiring_manager_content(context)
    if profile_content:
        return profile_content

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
    role_intent: Optional[Dict[str, Any]] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate and save a recruiter or hiring manager message."""
    normalized_type = message_type.replace("-", "_").lower()
    if normalized_type not in MESSAGE_TYPES:
        valid = ", ".join(message_type.replace("_", "-") for message_type in MESSAGE_TYPES)
        raise ApplicationMaterialError(f"Unknown message type '{message_type}'. Valid types: {valid}")

    context = load_generation_context(
        job_path,
        project_root,
        associated_evidence_projects=associated_evidence_projects,
        role_intent=role_intent,
    )
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
    role_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return generate_message("recruiter", job_path, project_root, role_intent)


def generate_hiring_manager_message(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    role_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return generate_message("hiring_manager", job_path, project_root, role_intent)
