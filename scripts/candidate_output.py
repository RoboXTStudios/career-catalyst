"""Candidate-facing realization for deterministic role-intent decisions.

Role intent remains an internal, inspectable structure.  This module is the
only place that turns those identifiers into prose shown to a candidate or an
employer.
"""

from __future__ import annotations

from html import unescape
import re
from typing import Any, Mapping, Sequence

try:
    from .evidence_tailoring import (
        cover_letter_project_paragraph,
        project_kind,
        project_title,
        relevant_selected_evidence,
        select_evidence_for_artifact,
    )
except ImportError:
    from evidence_tailoring import (
        cover_letter_project_paragraph,
        project_kind,
        project_title,
        relevant_selected_evidence,
        select_evidence_for_artifact,
    )


class CandidateOutputError(ValueError):
    """Raised when internal orchestration language reaches candidate copy."""


ARCHETYPE_LABELS = {
    "ai_transformation": "AI transformation and adoption",
    "marketing_operations_integration": "marketing operations integration",
    "shared_services_operations": "shared-services operations",
    "martech_governance_adoption": "MarTech governance and adoption",
    "business_operations_chief_of_staff": "business operations and executive enablement",
    "pmo_program_delivery": "program and portfolio delivery",
    "product_operations": "product operations",
    "product_marketing": "product marketing",
    "creative_operations": "creative operations",
    "entertainment_campaign_operations": "entertainment campaign operations",
    "editorial_content_operations": "editorial and content operations",
    "general_operations": "senior operations leadership",
}

EVIDENCE_LABELS = {
    "career_catalyst": "Career Catalyst product development",
    "ai_workflow_design": "AI workflow design",
    "structured_requirements": "structured requirements",
    "schemas_validation": "schemas and validation",
    "tested_workflows": "tested workflow development",
    "operational_workflow_design_airtable_implementation": "Airtable workflow implementation",
    "enterprise_collaboration_platform_adoption_stakeholder_enablement": "Microsoft Teams adoption",
    "disney_plus_launch_support": "Disney+ launch support",
    "campaignos_working_prototype": "CampaignOS working prototype",
    "workflow_governance": "workflow governance",
    "operating_standards": "operating standards",
    "cross_functional_leadership": "cross-functional leadership",
    "enterprise_campaign_delivery": "enterprise campaign delivery",
    "martech_campaign_execution": "MarTech campaign execution",
    "platform_implementation": "platform implementation",
    "measurement_readiness": "measurement readiness",
    "vendor_integration": "vendor integration",
    "executive_visibility": "executive decision visibility",
    "creative_management_leadership": "creative-management leadership",
    "roboxt_studios": "RoboXT Studios",
    "multiverse": "Multiverse editorial leadership",
    "editorial_strategy": "editorial strategy",
    "integrated_leadership": "integrated operational leadership",
    "fixed_timeline_delivery": "fixed-timeline delivery",
}

POLICY_LABELS = {
    "omit": "Omitted to keep the résumé focused",
    "compact_agency_only": "Two concise agency roles",
    "compact_relevant_only": "Only directly relevant earlier experience",
}

INTERNAL_PHRASES = (
    "work motions",
    "role signals",
    "required outcomes",
    "primary hiring need",
    "lead evidence",
    "supporting evidence",
    "suppressed evidence",
    "matched signals",
    "detected role",
    "role intent",
    "archetype",
    "fixture",
    "fundamentally about this operating need",
    "focus on improve",
)

CANDIDATE_FACING_QA_PHRASES = (
    "verified experience",
    "verified evidence",
    "candidate-facing provenance",
    "unsupported claim",
    "not supported",
    "claim ownership",
    "selected evidence records",
)


def humanize_identifier(value: Any) -> str:
    """Return an approved human label for an internal deterministic value."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw in ARCHETYPE_LABELS:
        return ARCHETYPE_LABELS[raw]
    if raw in EVIDENCE_LABELS:
        return EVIDENCE_LABELS[raw]
    if raw in POLICY_LABELS:
        return POLICY_LABELS[raw]
    words = raw.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def humanize_values(values: Sequence[Any]) -> list[str]:
    return [label for value in values if (label := humanize_identifier(value))]


def join_naturally(values: Sequence[str]) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def candidate_output_violations(
    text: str, *, include_candidate_qa_language: bool = True
) -> list[str]:
    """Find internal taxonomy or configuration syntax in candidate copy."""
    value = str(text or "")
    phrases = INTERNAL_PHRASES + (
        CANDIDATE_FACING_QA_PHRASES if include_candidate_qa_language else ()
    )
    found = [phrase for phrase in phrases if phrase in value.lower()]
    found.extend(
        match.group(0)
        for match in re.finditer(r"(?<![\w/])[a-z][a-z0-9]+(?:_[a-z0-9]+)+(?![\w/])", value)
    )
    return list(dict.fromkeys(found))


def validate_candidate_output(
    text: str,
    *,
    context: str = "candidate material",
    include_candidate_qa_language: bool = True,
) -> None:
    violations = candidate_output_violations(
        text, include_candidate_qa_language=include_candidate_qa_language
    )
    if violations:
        raise CandidateOutputError(
            f"{context} contains internal orchestration language: " + ", ".join(violations)
        )


def repair_candidate_output(text: str) -> str:
    """Repair identifiers when safe; semantic internal phrases remain rejectable."""
    return re.sub(
        r"(?<![\w/])[a-z][a-z0-9]+(?:_[a-z0-9]+)+(?![\w/])",
        lambda match: humanize_identifier(match.group(0)),
        str(text or ""),
    )


PROFILE_SUMMARIES = {
    "ai_transformation": (
        "Operations and transformation leader who translates user needs into governed AI-enabled workflows, "
        "structured requirements, validation practices, and adoption systems. Brings enterprise experience "
        "building practical operating models, guiding cross-functional teams, and testing new tools against "
        "real work so automation improves clarity and quality without displacing human judgment."
    ),
    "business_operations_chief_of_staff": (
        "Business operations and transformation leader who turns complex priorities into clear decisions, "
        "practical operating rhythms, and accountable cross-functional delivery. Advanced through five roles "
        "to Group Director at OMG23 / OMD Entertainment, Omnicom Media Group, leading 10 direct reports and providing strategic "
        "and operational leadership across an integrated 64-person organization supporting demanding "
        "entertainment portfolios."
    ),
    "general_operations": (
        "Senior operations and transformation leader who brings clarity, practical governance, and dependable "
        "execution to complex cross-functional work. Advanced through five roles to Group Director at OMG23 "
        "(Omnicom Media Group), leading 10 direct reports and providing strategic and operational leadership "
        "across an integrated 64-person organization spanning operations, creative management, and analytics."
    ),
}


BUSINESS_OPERATIONS_COMPETENCIES = [
    "Business Operations",
    "Strategic Operations",
    "Executive Stakeholder Management",
    "Cross-Functional Leadership",
    "Operating Model Design",
    "Decision Support",
    "Workflow Governance",
    "Program & Portfolio Leadership",
    "Risk Management",
    "Change Management",
    "Process Excellence",
    "Client Advisory",
]


def profile_summary(archetype: str, configured: str) -> str:
    if str(configured or "").strip():
        summary = str(configured).strip()
    elif archetype in PROFILE_SUMMARIES:
        summary = PROFILE_SUMMARIES[archetype]
    else:
        summary = (
            f"{configured.rstrip('.')} . "
            "Advanced through five roles to Group Director at OMG23 / OMD Entertainment, Omnicom Media Group, leading "
            "10 direct reports and providing strategic and operational leadership across an integrated "
            "64-person organization while coordinating complex work across creative, marketing, media, "
            "analytics, technology, vendors, and client stakeholders."
        ).replace(" .", ".")
    if len(summary.split()) < 55:
        summary += (
            " Known for clear communication, grounded recommendations, practical follow-through under pressure, "
            "stakeholder alignment, and turning broad priorities into visible, coordinated execution across complex "
            "creative, marketing, media, analytics, technology, and operations environments, with measurable outcomes "
            "and reliable decision support."
        )
    return summary


def competency_recipe(archetype: str) -> list[str] | None:
    if archetype == "business_operations_chief_of_staff":
        return list(BUSINESS_OPERATIONS_COMPETENCIES)
    return None


def domain_adjacency(parsed_job: Mapping[str, Any]) -> dict[str, bool]:
    text = " ".join(
        str(parsed_job.get(key) or "")
        for key in ("job_title", "raw_text", "job_description", "summary")
    ).lower()
    customer = any(
        phrase in text
        for phrase in ("customer experience", "customer success", "customer journey", "voice of customer")
    )
    traditional_saas = customer and any(
        phrase in text
        for phrase in ("renewal", "retention", "churn", "customer success platform", "saas")
    )
    return {"customer_experience": customer, "traditional_saas_customer_success": traditional_saas}


def tools_recipe(archetype: str, parsed_job: Mapping[str, Any]) -> dict[str, list[str]] | None:
    if archetype != "business_operations_chief_of_staff":
        return None
    if domain_adjacency(parsed_job)["customer_experience"]:
        return {
            "Collaboration & Workflow Platforms": [
                "Airtable", "Microsoft Teams", "Microsoft 365", "Box", "Trello"
            ],
            "Operations Practices": [
                "Operating Models", "Workflow Design", "Process Documentation",
                "Reporting Workflows", "Governance", "Training", "Adoption",
            ],
        }
    return {
        "Operations Practices": [
            "Operating Models", "Workflow Design", "Process Documentation",
            "Reporting Workflows", "Governance", "Training", "Adoption",
        ]
    }


COMMON_EVIDENCE = {
    "leadership": "Led 10 direct reports and provided strategic and operational leadership across an integrated 64-person organization spanning Ad Operations, Creative Management, and Marketing Science and Analytics.",
    "operating_plans": "Translated senior leadership and client priorities into operating plans, governance, decision paths, stakeholder reporting, and cross-functional execution.",
    "progression": "Advanced through five roles from Campaign Manager to Group Director while expanding responsibility across enterprise operations and transformation.",
    "delivery": "Directed operational execution for multimillion-dollar theatrical, streaming, and franchise campaigns, coordinating priorities, dependencies, quality, and stakeholder visibility.",
    "governance": "Introduced scalable workflows, governance practices, and execution standards across marketing, technology, analytics, and creative teams.",
    "airtable": "Coordinated an Airtable implementation that created a shared source of truth for campaign tracking, documentation, status reporting, linked workflows, permissions, naming standards, automations, quality assurance, training, and adoption.",
    "disney_plus": "Helped operationalize the Disney+ launch through onboarding, quality assurance, measurement readiness, platform coordination, and execution workflows.",
}

EVIDENCE_RECIPES = {
    "business_operations_chief_of_staff": ("leadership", "operating_plans", "airtable", "governance", "delivery", "progression"),
    "pmo_program_delivery": ("delivery", "disney_plus", "governance", "leadership", "airtable", "progression"),
    "shared_services_operations": ("leadership", "governance", "airtable", "delivery", "progression", "disney_plus"),
    "martech_governance_adoption": ("governance", "disney_plus", "airtable", "delivery", "leadership", "progression"),
    "marketing_operations_integration": ("leadership", "airtable", "governance", "delivery", "progression", "disney_plus"),
    "product_operations": ("airtable", "governance", "leadership", "delivery", "progression", "disney_plus"),
    "product_marketing": ("delivery", "disney_plus", "leadership", "governance", "progression", "airtable"),
    "creative_operations": ("leadership", "delivery", "governance", "progression", "airtable", "disney_plus"),
    "entertainment_campaign_operations": ("delivery", "disney_plus", "leadership", "governance", "progression", "airtable"),
    "editorial_content_operations": ("leadership", "progression", "governance", "delivery", "airtable", "disney_plus"),
    "ai_transformation": ("leadership", "airtable", "disney_plus", "governance", "delivery", "progression"),
    "general_operations": ("leadership", "progression", "governance", "delivery", "airtable", "disney_plus"),
}


def evidence_recipe(archetype: str, limit: int = 6) -> list[str]:
    keys = EVIDENCE_RECIPES.get(archetype, EVIDENCE_RECIPES["general_operations"])
    return [COMMON_EVIDENCE[key] for key in keys[:limit]]


def _product_evidence_cover_letter(
    context: Mapping[str, Any], projects: Sequence[Mapping[str, Any]]
) -> str:
    parsed = context["parsed_job"]
    intent = context["role_intent"]
    company = str(parsed.get("company") or "your organization")
    role = str(parsed.get("job_title") or "product strategy role")
    greeting = str((intent.get("cover_letter") or {}).get("greeting") or "Dear Hiring Team,")
    selected = relevant_selected_evidence(projects, parsed, limit=2)
    project_paragraphs = [
        paragraph
        for project in selected
        if (paragraph := cover_letter_project_paragraph(project, parsed))
    ]
    parsed_text = " ".join(
        str(parsed.get(key) or "")
        for key in ("job_title", "raw_text", "job_description")
    ).lower()
    emerging_formats = any(
        signal in parsed_text
        for signal in ("emerging format", "podcast", "live streaming", "content lifecycle")
    )
    opening = (
        f"I am interested in the {role} role at {company} because emerging formats require product "
        "judgment that connects audience and content needs with technology, analytics, and dependable "
        "cross-functional execution. My background combines entertainment launch readiness, ambiguous-"
        "requirements translation, active product development, and hands-on media production."
        if emerging_formats
        else (
            f"I am interested in the {role} role at {company} because it calls for product judgment that "
            "connects user and business needs with clear requirements, priorities, quality controls, and "
            "dependable cross-functional execution. My background combines entertainment launch readiness, "
            "ambiguous-requirements translation, active product development, and practical operations."
        )
    )
    leadership = (
        "At OMG23 / OMD Entertainment, Omnicom Media Group, I advanced through five roles to Group Director, led 10 direct "
        "reports, and provided strategic and operational leadership across an integrated 64-person "
        "organization. I also supported Disney+ launch readiness through governance, platform coordination, "
        "quality assurance, tracking, and measurement readiness across creative, media, technology, and "
        "analytics partners."
    )
    product_bridge = (
        "Across those programs, I learned to turn unclear goals into sequenced decisions, surface "
        "dependencies and tradeoffs early, and keep content, technology, analytics, and operations partners "
        "aligned around launch-ready work. That operating discipline complements the hands-on product and "
        + (
            "production evidence I would bring to an emerging-formats team."
            if emerging_formats
            else "delivery evidence I would bring to a product organization."
        )
    )
    closing = (
        f"I would bring {company} grounded product thinking, clear requirements, thoughtful tradeoff "
        "management, and calm cross-functional leadership. I would welcome the opportunity to discuss how "
        + (
            "that combination could help the team shape and deliver engaging emerging-format experiences."
            if emerging_formats
            else "that combination could help the team shape priorities and deliver useful product outcomes."
        )
    )
    content = "\n\n".join(
        [
            greeting,
            opening,
            leadership,
            product_bridge,
            *project_paragraphs,
            closing,
            "Best,\n\nTrisha Lynch",
        ]
    )
    validate_candidate_output(content, context="Generated cover letter")
    return content


def _configured_project_evidence(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    configured_names = list(
        (context.get("role_intent") or {}).get("resume", {}).get("selected_project_ids")
        or []
    )
    career_projects = (
        (context.get("career_data") or {}).get("data", {}).get("projects", {}).get("projects", [])
        or []
    )
    projects: list[dict[str, Any]] = []
    for name in configured_names:
        project = next(
            (item for item in career_projects if str(item.get("name") or "") == str(name)),
            None,
        )
        if not project:
            continue
        projects.append(
            {
                "id": str(project.get("id") or name),
                "title": str(project.get("name") or name),
                "project_type": str(project.get("role") or "Independent product work"),
                "actions": str(project.get("summary") or ""),
                "results": list(project.get("highlights") or []),
                "tags": ["Product Development", "Workflow Design"],
                "manual": False,
            }
        )
    return projects


def cover_letter_evidence_decision(
    context: Mapping[str, Any], *, limit: int = 2
) -> dict[str, Any]:
    """Use the shared selector with manual selections ahead of disclosed fallbacks."""
    selected_projects = list(context.get("associated_evidence_projects") or [])
    allow_legacy_product_fallback = (
        not selected_projects
        and str((context.get("role_intent") or {}).get("primary_archetype") or "")
        == "product_operations"
    )
    return select_evidence_for_artifact(
        context["parsed_job"],
        selected_projects,
        artifact_type="cover_letter",
        capacity=limit,
        fallback_projects=_configured_project_evidence(context),
        minimum_selected=min(2, limit) if allow_legacy_product_fallback else 0,
    )


def cover_letter_evidence_selection(
    context: Mapping[str, Any], *, limit: int = 2
) -> list[dict[str, Any]]:
    """Return projects selected by the shared Evidence orchestration service."""
    return cover_letter_evidence_decision(context, limit=limit)["used_projects"]


def candidate_cover_letter(context: Mapping[str, Any]) -> str:
    """Build natural, grounded general-role copy without exposing orchestration data."""
    parsed = dict(context["parsed_job"])
    for field in ("job_title", "company", "role"):
        if field in parsed and parsed[field] is not None:
            parsed[field] = unescape(str(parsed[field]))
    intent = context["role_intent"]
    company = str(parsed.get("company") or "your organization")
    role = str(parsed.get("job_title") or "senior operations role")
    greeting = str((intent.get("cover_letter") or {}).get("greeting") or "Dear Hiring Team,")
    archetype = str(intent.get("primary_archetype") or "general_operations")
    role_family = str(
        intent.get("package_role_family")
        or (context.get("role_intelligence") or {}).get("role_family")
        or ""
    )
    if role_family == "strategy_gtm_operations":
        return _strategy_gtm_cover_letter(context, greeting, company, role)
    if role_family == "music_partnerships_label_relations":
        return _music_partnerships_cover_letter(context, greeting, company, role)
    if role_family == "experiential_live_event_production":
        return _experiential_cover_letter(context, greeting, company, role)
    adjacency = domain_adjacency(parsed)
    if archetype == "product_operations":
        selected_projects = cover_letter_evidence_selection(context)
        if selected_projects:
            return _product_evidence_cover_letter(context, selected_projects)

    if adjacency["customer_experience"]:
        opening = (
            f"The {role} role at {company} calls for someone who can turn complex priorities into clear decisions, "
            "accountable plans, and sustained cross-functional follow-through. That has been the through line of my work: "
            "helping leaders and specialized teams move from competing inputs to shared priorities, visible dependencies, "
            "and practical execution."
        )
    else:
        opening = (
            f"I am interested in the {role} role at {company} because it calls for the combination of "
            f"{ARCHETYPE_LABELS.get(archetype, 'senior operations leadership')}, sound judgment, and "
            "cross-functional follow-through that has defined my work. I am most effective when leaders need "
            "shared priorities, clear ownership, useful operating visibility, and systems that help people make better decisions."
        )
    leadership = (
        "At OMG23 / OMD Entertainment, Omnicom Media Group, I advanced through five roles to Group Director. I led 10 direct "
        "reports and provided strategic and operational leadership across an integrated 64-person organization "
        "spanning Ad Operations, Creative Management, and Marketing Science and Analytics. The work required "
        "translating demanding client and leadership priorities into accountable plans across creative, media, "
        "analytics, technology, vendors, and client stakeholders."
    )
    execution = (
        "I built governance, quality standards, decision paths, and reporting practices for multimillion-dollar "
        "theatrical and streaming campaigns. I also coordinated an Airtable implementation as a shared source "
        "of truth and supported Microsoft Teams adoption through guidance, office hours, troubleshooting, and a "
        "peer champion network. These efforts paired platform changes with documentation, training, and adoption."
    )
    if archetype == "pmo_program_delivery":
        execution = (
            "I built governance, quality standards, and reporting practices for multimillion-dollar theatrical "
            "and streaming campaigns, keeping milestones, dependencies, risks, and decisions visible across "
            "creative, media, analytics, technology, vendors, and client stakeholders. I also helped operationalize "
            "the Disney+ launch under a fixed timeline, connecting quality assurance, measurement readiness, "
            "platform coordination, and accountable execution."
        )
    if adjacency["customer_experience"]:
        proof = (
            "While my background is rooted in enterprise marketing operations, the strategic work is highly transferable "
            "to Customer Experience: executive decision support, cross-functional program leadership, governance, "
            "stakeholder alignment, and measurable follow-through. I have mapped stakeholder needs, improved handoffs, "
            "surfaced recurring friction, and used feedback to strengthen service delivery across complex client environments."
        )
    else:
        proof = (
            "That experience taught me to diagnose the operating problem before prescribing a tool, clarify who "
            "owns each decision, and keep risks visible without adding unnecessary process. It is a practical, "
            "advisory approach grounded in implementation as well as recommendation."
        )
    if adjacency["customer_experience"]:
        closing = (
            f"I would bring {company} calm senior judgment, factual communication, and a disciplined approach to "
            "turning priorities into measurable, consistent progress. I would value the opportunity to discuss how this experience "
            "could support the Customer Experience organization."
        )
    else:
        closing = (
            f"I would bring {company} calm senior judgment, factual communication, and a disciplined approach to "
            "turning priorities into measurable, consistent progress. I would value the opportunity to discuss how this experience "
            f"could support the {role} team."
        )
    content = "\n\n".join((greeting, opening, leadership, execution, proof, closing, "Best,\n\nTrisha Lynch"))
    validate_candidate_output(content, context="Generated cover letter")
    return content


def _experiential_cover_letter(
    context: Mapping[str, Any], greeting: str, company: str, role: str
) -> str:
    """Translate grounded operations experience toward an experiential role."""
    parsed = context["parsed_job"]
    projects = _selected_project_paragraphs(context, parsed)
    content = "\n\n".join(
        [
            greeting,
            (
                f"The {role} opportunity at {company} stands out because it brings together creative activation, "
                "production coordination, and live-event delivery. My background is in senior entertainment and "
                "marketing operations, where I have built the planning, workflow, and stakeholder practices that "
                "help complex work move from brief to execution."
            ),
            (
                "At OMG23 / OMD Entertainment, Omnicom Media Group, I advanced through five roles to Group Director, led 10 direct "
                "reports, and provided strategic and operational leadership across an integrated 64-person "
                "organization spanning Ad Operations, Creative Management, and Marketing Science and Analytics. "
                "I translated demanding priorities into accountable plans, quality standards, timelines, and "
                "cross-functional delivery across creative, media, analytics, technology, vendors, and client teams."
            ),
            (
                "That foundation is transferable to experiential production. I would bring structured planning, "
                "clear ownership, timeline visibility, stakeholder coordination, and practical follow-through to "
                "activation work while respecting the specialized production expertise already on the team."
            ),
            *projects,
            (
                f"I would welcome the chance to learn how {company} is shaping this work and where the team needs "
                "the most dependable operating support. I would bring calm senior judgment, creative respect, and "
                "a disciplined approach to helping people coordinate complex delivery."
            ),
            "Best,\n\nTrisha Lynch",
        ]
    )
    validate_candidate_output(content, context="Generated experiential cover letter")
    return content


def _selected_project_paragraphs(
    context: Mapping[str, Any], parsed: Mapping[str, Any], limit: int = 2
) -> list[str]:
    decision = cover_letter_evidence_decision(context, limit=limit)
    return [
        paragraph
        for project in decision.get("used_projects", [])
        if (paragraph := cover_letter_project_paragraph(project, parsed))
    ]


def _strategy_gtm_cover_letter(
    context: Mapping[str, Any], greeting: str, company: str, role: str
) -> str:
    parsed = context["parsed_job"]
    selected_projects = cover_letter_evidence_selection(context)
    projects = [
        paragraph
        for project in selected_projects
        if (paragraph := cover_letter_project_paragraph(project, parsed))
    ]
    airtable_selected = any(
        "airtable" in " ".join(
            str(project.get(key) or "") for key in ("id", "title", "name")
        ).lower()
        for project in selected_projects
    )
    airtable_proof = [] if airtable_selected else [
        (
            "I also coordinated an Airtable implementation that created a shared source of truth for campaign tracking, "
            "workflow documentation, status reporting, permissions, quality assurance, training, and adoption. That "
            "work strengthened my ability to improve visibility without adding unnecessary process, while keeping "
            "owners aligned around the decisions that affect delivery."
        )
    ]
    content = "\n\n".join(
        [
            greeting,
            (
                f"I am applying for the {role} role at {company} because it connects planning, operating visibility, "
                "data quality, and cross-functional execution. My experience is strongest where leaders need a clear "
                "view of priorities, dependencies, decisions, and the work required to move them forward."
            ),
            (
                "At OMG23 / OMD Entertainment, Omnicom Media Group, I advanced through five roles to Group Director, led 10 direct reports, "
                "and provided strategic and operational leadership across an integrated 64-person organization spanning "
                "Ad Operations, Creative Management, and Marketing Science and Analytics. I translated complex client and "
                "leadership priorities into operating plans, governance, reporting, and accountable execution across "
                "creative, media, analytics, technology, vendors, and client stakeholders."
            ),
            *airtable_proof,
            *projects,
            (
                "Together, these examples show how I connect strategic planning with dependable "
                "operating systems and disciplined follow-through."
            ),
            (
                "In a strategy and operations setting, I would apply that same discipline to planning cadence, data and "
                "workflow quality, executive reporting, and the handoffs that connect Sales, Finance, Marketing, and other "
                "partners. I would keep the work grounded in the team's actual operating needs and make progress visible "
                "while staying precise about the scope of my direct experience."
            ),
            (
                f"I would bring {company} practical operating judgment, clear communication, and a structured approach to "
                "turning priorities into visible, measurable execution."
            ),
            "Best,\n\nTrisha Lynch",
        ]
    )
    validate_candidate_output(content, context="Generated strategy and operations cover letter")
    return content


def _music_partnerships_cover_letter(
    context: Mapping[str, Any], greeting: str, company: str, role: str
) -> str:
    parsed = context["parsed_job"]
    projects = _selected_project_paragraphs(context, parsed)
    content = "\n\n".join(
        [
            greeting,
            (
                f"I am applying for the {role} role at {company} because it sits at the intersection of music, creators, "
                "platform collaboration, and dependable partner execution. My background combines hands-on audio "
                "production with senior entertainment-media operations, giving me both respect for the work itself and "
                "a practical understanding of the coordination required around it."
            ),
            (
                "At OMG23 / OMD Entertainment, Omnicom Media Group, I advanced to Group Director, led 10 direct reports, and provided strategic "
                "and operational leadership across an integrated 64-person organization spanning Ad Operations, Creative "
                "Management, and Marketing Science and Analytics. I coordinated priorities, quality standards, reporting, "
                "and stakeholder communication across creative, media, analytics, technology, vendors, and client teams."
            ),
            (
                "My direct experience is in audio production, entertainment-media operations, and cross-functional partner "
                "coordination. I would bring that foundation to label-facing work with respect for the commercial and "
                "relationship expertise the role requires, along with a careful, organized approach to partner communication "
                "and execution."
            ),
            (
                "Audio production also sharpened my attention to voice, timing, audience experience, and the details that "
                "make a collaborative release dependable. I would carry that care into partner communication, release "
                "readiness, escalation follow-through, and the practical coordination required when several teams share an "
                "outcome."
            ),
            (
                "In a music-partnership setting, I would contribute disciplined preparation, clear communication, release "
                "readiness, and thoughtful coordination across the people responsible for a shared outcome. My goal would "
                "be to make collaboration easier while respecting the specialized relationship knowledge already present "
                "across the team."
            ),
            (
                "The combination of production detail and operational coordination is useful when partner needs, creative "
                "priorities, platform requirements, and timing all intersect. I would approach that work with careful "
                "listening, clear documentation, and consistent follow-through from planning through release."
            ),
            (
                f"I would bring {company} thoughtful coordination, clear follow-through, and genuine respect for the music "
                "and creator ecosystem this role serves."
            ),
            "Best,\n\nTrisha Lynch",
        ]
    )
    validate_candidate_output(content, context="Generated music partnerships cover letter")
    return content
