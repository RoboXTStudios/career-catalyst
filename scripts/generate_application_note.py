"""Generate a short, grounded note for application portals."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .career_claims import leadership_claim, public_omg23_name
    from .generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )
    from .role_context import is_google_youtube_role
    from .evidence_tailoring import project_kind
except ImportError:
    from career_claims import leadership_claim, public_omg23_name
    from generate_cover_letter import (
        _position,
        load_generation_context,
        save_material,
    )
    from role_context import is_google_youtube_role
    from evidence_tailoring import project_kind


PathInput = Union[str, Path]

DYNAMIC_NOTE_FOCUS = {
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


def _has_selected_project(context: Dict[str, Any], kind: str) -> bool:
    return any(
        project_kind(project) == kind
        for project in context.get("associated_evidence_projects") or []
    )


def _openai_sales_operations_note(context: Dict[str, Any]) -> str:
    career_catalyst = (
        " Through Career Catalyst, I am actively developing an AI-enabled career intelligence and "
        "application-operations product, translating user needs into product requirements, tested "
        "workflows, acceptance criteria, and release guardrails."
        if _has_selected_project(context, "career_catalyst")
        else ""
    )
    return (
        "OpenAI's Sales Strategy & Operations - Central role interests me because it brings disciplined "
        "planning, operating visibility, and cross-functional execution to a fast-moving go-to-market "
        "environment. At OMG23 (Omnicom Media Group), I advanced through five roles to Group Director, "
        "led 10 direct reports, and provided strategic and operational leadership across an integrated "
        "64-person organization spanning Ad Operations, Creative Management, and Marketing Science and "
        "Analytics. I also coordinated an Airtable implementation that created a shared source of truth "
        "for campaign tracking, reporting, workflow governance, quality assurance, training, and adoption, "
        "and I helped operationalize Disney+ launch readiness across multiple functions."
        f"{career_catalyst} These are direct examples of enterprise operating discipline and hands-on AI "
        "product development. My experience is transferable rather than identical to sales operations: "
        "I have not owned quotas, territory design, compensation plans, sales forecasts, Salesforce "
        "administration, or revenue operations, and I would bring a clear learning approach to those "
        "domain-specific responsibilities."
    )


def _twitch_label_relations_note(context: Dict[str, Any]) -> str:
    podcast = (
        " I served as audio producer and editor for Just for Us, a ten-episode, multi-host podcast series "
        "released on Spotify. I handled dialogue editing, pacing, audio balancing, revisions, quality "
        "control, and release-ready delivery."
        if _has_selected_project(context, "podcast")
        else ""
    )
    return (
        "Twitch's Senior Label Relations Manager role interests me because it connects music, creators, "
        "platform collaboration, and dependable partner execution."
        f"{podcast} At OMG23 (Omnicom Media Group), I led 10 direct reports and provided strategic and "
        "operational leadership across an integrated 64-person organization while coordinating work "
        "across creative, media, analytics, technology, vendors, and client stakeholders. Through "
        "Enterprise Media Operations Transformation, I led workflow design and stakeholder alignment, "
        "and this work improved visibility, execution quality, and delivery consistency. My direct "
        "experience is in audio production, entertainment-media operations, and stakeholder coordination; "
        "it is transferable to label-facing work, but I am not presenting myself as an established "
        "label-relations executive. I have not owned label accounts, managed artists, negotiated label or "
        "artist deals, owned commercial forecasting, or held direct music-industry business-development "
        "responsibility."
    )


def _profile_application_note(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    profile_key = context.get("profile_key", "default")
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "This opportunity"
    notes = {
        "disney": (
            f"The {role} role at {company} caught my attention because it connects product and "
            "technology strategy, OKRs, and executive operating rhythms within a large entertainment "
            "ecosystem. My Disney Studios Theatrical and Disney Streaming/DSS experience gives me "
            "practical context for that scale. I have aligned creative, marketing, analytics, technology, "
            "and operations partners, and built CampaignOS to improve workflow governance, validation, "
            "and operational visibility."
        ),
        "paramount": (
            f"The {role} role at {company} stood out because marketing operations is the connective "
            f"layer between strategy, creative capacity, and delivery. I {leadership_claim(context['career_data'])} "
            "and built workflows, standards, dashboards, and AI-enabled "
            "quality systems. CampaignOS is a current example of how I turn recurring delivery friction "
            "into clearer operations and better decision support."
        ),
        "uta": (
            f"The {role} role at {company} stood out because it combines transformation advisory, "
            "operating models, stakeholder management, and strategy into execution. My background spans "
            "media, marketing, advertising, and technology, with experience translating senior stakeholder "
            "priorities into practical recommendations and delivery systems. Building CampaignOS further "
            "developed my hypothesis-driven approach to organizational problems, client-ready communication, "
            "and disciplined work from discovery through implementation."
        ),
        "fieldai": (
            f"The {role} role at {company} caught my attention because it centers on matrix operations, "
            f"organizational efficiency, capacity visibility, and operating cadences. I {leadership_claim(context['career_data'])} "
            "and built governance, dashboards, automation, and quality systems across several functions. "
            "CampaignOS reflects my AI-forward approach to making workflows, risk, and decisions clearer "
            "at scale without adding unnecessary process."
        ),
        "bandsintown": (
            f"The {role} role at {company} stood out because it connects music, audience understanding, "
            "editorial voice, and content systems. Alongside leading entertainment marketing work, I created "
            "and managed Multiverse, an editorial publication centered on creativity, culture, music, and "
            "innovation. Through RoboXT Studios, I continue developing creative and publishing systems across "
            "photography, editorial work, technology, and AI. I bring both creative instinct and operational discipline."
        ),
        "crunchyroll": (
            f"The {role} role at {company} caught my attention because it connects streaming, fandom, "
            "franchise/IP, and enterprise strategy. I have led theatrical and streaming entertainment "
            "work across creative, marketing, media, analytics, technology, and operations. CampaignOS adds "
            "a current systems proof point for how I turn cross-functional priorities into clearer governance, "
            "validation, reporting, and scalable execution with a grounded audience perspective."
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
    position_company = public_omg23_name(career_data)
    title = str(role or "").lower()

    if company.lower() == "openai" and "sales strategy" in title and "operations" in title:
        return _openai_sales_operations_note(context)
    if company.lower() == "twitch" and "label relations" in title:
        return _twitch_label_relations_note(context)

    if is_google_youtube_role(parsed_job):
        return (
            "This Google opportunity caught my attention because it connects YouTube product "
            "activation, GTM operations, and large advertiser execution. I bring long-term hands-on "
            "experience with Google advertising products, including YouTube, dating back to the "
            "early 2000s. I have translated platform capabilities into campaign execution, "
            "measurement readiness, and operational workflows across large entertainment advertisers. "
            "That foundation aligns with Brand Auction activation, seller enablement, senior stakeholder "
            "alignment, and product feedback loops. CampaignOS adds a current proof point for my "
            "operational systems thinking."
        )

    profile_note = _profile_application_note(context)
    if profile_note:
        return profile_note

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
                "I created and managed Multiverse, continue developing creative publishing systems through RoboXT Studios, "
                "and bring large-scale entertainment marketing experience."
            )
        else:
            proof = (
                f"I {leadership_claim(career_data)} and built workflow governance, execution "
                "standards, dashboards, and CampaignOS systems at scale."
            )
        return (
            f"The {role} role at {company} caught my attention because it centers on {focus}. "
            f"{proof} I would bring calm senior judgment, practical systems thinking, and a grounded "
            "approach based on the role's stated priorities rather than assumptions about the company."
        )

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
    role_intent: Optional[Dict[str, Any]] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate and save a short application portal note."""
    context = load_generation_context(
        job_path,
        project_root,
        associated_evidence_projects=associated_evidence_projects,
        role_intent=role_intent,
    )
    return save_material(
        context,
        "Application_Note",
        additional_information_content(_application_note_content(context)),
        minimum_words=60,
        maximum_words=230,
    )


def additional_information_content(content: str) -> str:
    """Format a concise portal response, never a second cover letter."""
    body = " ".join(str(content or "").strip().split())
    return "Additional Information\n" + body
