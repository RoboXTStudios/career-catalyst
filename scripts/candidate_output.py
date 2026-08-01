"""Candidate-facing realization for deterministic role-intent decisions.

Role intent remains an internal, inspectable structure.  This module is the
only place that turns those identifiers into prose shown to a candidate or an
employer.
"""

from __future__ import annotations

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


def candidate_output_violations(text: str) -> list[str]:
    """Find internal taxonomy or configuration syntax in candidate copy."""
    value = str(text or "")
    found = [phrase for phrase in INTERNAL_PHRASES if phrase in value.lower()]
    found.extend(
        match.group(0)
        for match in re.finditer(r"(?<![\w/])[a-z][a-z0-9]+(?:_[a-z0-9]+)+(?![\w/])", value)
    )
    return list(dict.fromkeys(found))


def validate_candidate_output(text: str, *, context: str = "candidate material") -> None:
    violations = candidate_output_violations(text)
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
        "to Group Director at OMG23 (Omnicom Media Group), leading 10 direct reports and providing strategic "
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
    if archetype in PROFILE_SUMMARIES:
        summary = PROFILE_SUMMARIES[archetype]
    else:
        summary = (
            f"{configured.rstrip('.')} . "
            "Advanced through five roles to Group Director at OMG23 (Omnicom Media Group), leading "
            "10 direct reports and providing strategic and operational leadership across an integrated "
            "64-person organization while coordinating complex work across creative, marketing, media, "
            "analytics, technology, vendors, and client stakeholders."
        ).replace(" .", ".")
    if len(summary.split()) < 55:
        summary += " Known for clear communication, grounded recommendations, and practical follow-through under pressure."
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
        "At OMG23 (Omnicom Media Group), I advanced through five roles to Group Director, led 10 direct "
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
    parsed = context["parsed_job"]
    intent = context["role_intent"]
    company = str(parsed.get("company") or "your organization")
    role = str(parsed.get("job_title") or "senior operations role")
    greeting = str((intent.get("cover_letter") or {}).get("greeting") or "Dear Hiring Team,")
    archetype = str(intent.get("primary_archetype") or "general_operations")
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
        "At OMG23 (Omnicom Media Group), I advanced through five roles to Group Director. I led 10 direct "
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
