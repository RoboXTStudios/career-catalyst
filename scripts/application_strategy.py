"""Interpretation-aware hiring lens, evidence strategy, and material gates."""

from __future__ import annotations

import re
from typing import Any, Iterable


TECHNICAL_ARCHETYPES = {
    "Technical Solutions / Solutions Consulting",
    "Advertising Technology / Ad Operations",
    "Implementation / Onboarding",
    "Sales Engineering",
    "Technical Program Management",
}


ARCHETYPE_EVIDENCE_PRIORITIES: dict[str, tuple[str, ...]] = {
    "Technical Solutions / Solutions Consulting": (
        "adtech", "martech", "campaign_execution", "measurement", "qa",
        "cross_functional_leadership", "team_leadership", "platform activation",
        "troubleshooting", "implementation", "client issue resolution",
    ),
    "Advertising Technology / Ad Operations": (
        "adtech", "martech", "campaign_execution", "measurement", "qa",
        "entertainment_marketing_operations", "platform activation", "campaign delivery",
    ),
    "Implementation / Onboarding": (
        "qa", "usable_standards", "change_adoption", "cross_functional_leadership",
        "systems_built", "implementation", "partner coordination",
    ),
    "Sales Engineering": (
        "adtech", "martech", "measurement", "cross_functional_leadership",
        "product_thinking", "platform activation", "client trust",
    ),
    "Strategic Operations": (
        "governance", "pmo", "ambiguity_reduction", "ownership_clarity",
        "cross_functional_leadership", "decision support", "operating cadence",
    ),
    "Chief of Staff": (
        "governance", "pmo", "ambiguity_reduction", "ownership_clarity",
        "cross_functional_leadership", "executive visibility", "decision support",
    ),
    "Product Operations": (
        "product_thinking", "systems_built", "qa", "governance", "change_adoption",
        "cross_functional_leadership", "launch readiness", "feedback systems",
    ),
    "People Operations": (
        "team_leadership", "team_enablement", "change_adoption", "employee_communication",
        "usable_standards", "cross_functional_leadership",
    ),
}


ROLE_LANGUAGE: dict[str, tuple[str, ...]] = {
    "Technical Solutions / Solutions Consulting": (
        "technical solutions", "technical problem", "troubleshoot", "implementation",
        "integration", "platform adoption", "client", "customer", "advertiser",
        "product and engineering", "measurement",
    ),
    "Advertising Technology / Ad Operations": (
        "advertising technology", "ad tech", "adtech", "campaign delivery", "measurement",
        "pixel", "conversions api", "advertiser", "platform activation", "troubleshoot",
    ),
    "Implementation / Onboarding": (
        "implementation", "onboarding", "integration", "configuration", "go live",
        "customer", "adoption", "deployment",
    ),
    "Sales Engineering": (
        "sales engineering", "technical discovery", "solution design", "customer",
        "technical", "product demonstration", "proof of concept",
    ),
    "Strategic Operations": (
        "decision support", "business planning", "operating cadence", "executive priorities",
        "strategic initiatives", "cross-functional execution",
    ),
    "Chief of Staff": (
        "executive", "decision support", "leadership cadence", "priority", "briefing", "follow-through",
    ),
    "Product Operations": (
        "product operations", "launch", "product feedback", "feedback loop",
        "product adoption", "product activation", "seller enablement", "gtm operations",
        "governance", "product and engineering",
    ),
    "People Operations": (
        "people operations", "employee", "manager enablement", "employee lifecycle", "people systems", "hr",
    ),
}


GENERIC_OPERATIONS_FALLBACK = (
    "operating structures",
    "planning rhythms",
    "ownership clarity",
    "stakeholder alignment",
    "governance without bureaucracy",
    "translating priorities into execution",
    "senior leadership support",
    "communication routines",
    "operational traction",
    "operating cadence",
    "clear ownership",
)


OPERATIONS_ARCHETYPES = {
    "General Business Operations",
    "Strategic Operations",
    "Chief of Staff",
    "Program / Project Management",
    "Transformation / Operational Excellence",
}


UNSUPPORTED_TECHNICAL_CLAIMS = (
    "managed solutions engineers",
    "led solutions engineers",
    "developed apis",
    "built apis",
    "owned api development",
    "implemented sdks",
    "sdk implementation",
    "solution architecture ownership",
    "software engineering leadership",
    "technical sales ownership",
)


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip(" -:;.")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _unsupported_assertions(content: str) -> list[str]:
    """Return technical-ownership phrases only when they are asserted, not disclaimed."""
    lowered = str(content or "").lower()
    assertions: list[str] = []
    for claim in UNSUPPORTED_TECHNICAL_CLAIMS:
        for match in re.finditer(re.escape(claim), lowered):
            prefix = lowered[max(0, match.start() - 90) : match.start()]
            sentence_prefix = re.split(r"[.!?;]", prefix)[-1]
            if re.search(r"\b(?:do|would|did|have|has|had|can|could) not\b|\bnot claim\b|\bwithout (?:claiming|implying)\b", sentence_prefix):
                continue
            assertions.append(claim)
            break
    return assertions


def evidence_priorities(archetype: Any) -> list[str]:
    return list(
        ARCHETYPE_EVIDENCE_PRIORITIES.get(
            str(archetype or ""),
            ("cross_functional_leadership", "measurable_impact", "usable_standards"),
        )
    )


def build_hiring_manager_lens(
    interpretation: dict[str, Any],
    alignment_matrix: list[dict[str, Any]] | None = None,
    gap_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate one confirmed interpretation into a role-specific hiring-manager view."""
    archetype = str(interpretation.get("primary_archetype") or "General Business Operations")
    explicit = [str(value) for value in interpretation.get("true_must_haves") or []]
    common = {
        "Technical Solutions / Solutions Consulting": {
            "problem": "Make technically complex products reliable and usable for customers while turning recurring issues into product and support improvements.",
            "ideal": "A technical client-solutions leader who can earn trust with customers and engineers, troubleshoot under pressure, and lead specialists without losing execution detail.",
            "yes": ["technical implementation fluency", "credible troubleshooting examples", "client trust during escalations", "translation between customers, sales, product, and engineering", "platform adoption and measurement knowledge"],
            "hesitations": ["general operations experience presented as a substitute for technical-solutions depth", "unclear hands-on implementation experience", "no evidence of customer-facing technical problem-solving"],
            "probes": ["hands-on advertising-technology implementation", "a complex platform or campaign issue resolved", "translation of technical requirements for nontechnical partners", "management of technical specialists"],
            "fail": "A candidate who speaks fluently about process but cannot diagnose customer technical problems or earn credibility with product and engineering.",
        },
        "Advertising Technology / Ad Operations": {
            "problem": "Keep advertising delivery, measurement signals, and advertiser implementations reliable at scale.",
            "ideal": "An ad-tech operator who understands campaign delivery and measurement, can resolve technical blockers, and can coordinate advertisers, sales, product, and engineering.",
            "yes": ["ad-tech and programmatic depth", "measurement and signal readiness", "campaign troubleshooting", "advertiser-facing judgment", "reliable implementation and QA practices"],
            "hesitations": ["limited direct implementation ownership", "process language without ad-tech substance", "overstated API, SDK, or engineering claims"],
            "probes": ["pixel or Conversions API implementation depth", "campaign delivery troubleshooting", "advertiser escalation handling", "technical-team leadership"],
            "fail": "A broad operator who cannot distinguish campaign process improvement from technical advertising problem-solving.",
        },
        "Strategic Operations": {
            "problem": "Turn executive priorities into decision-ready analysis, operating cadence, and accountable cross-functional execution.",
            "ideal": "A strategic operator who can synthesize ambiguity, support decisions, prioritize work, and create follow-through without unnecessary process.",
            "yes": ["executive decision support", "business planning", "operating cadence", "clear prioritization", "cross-functional follow-through"],
            "hesitations": ["strong facilitation without analytical depth", "process creation disconnected from business outcomes"],
            "probes": ["a consequential leadership decision supported", "a planning cadence improved", "competing priorities resolved", "analysis translated into execution"],
            "fail": "A coordinator who tracks work but does not improve decisions, prioritization, or business outcomes.",
        },
        "Product Operations": {
            "problem": "Make product planning, launches, feedback, tooling, and governance work consistently across product teams.",
            "ideal": "A product-facing operator who improves launch readiness, feedback systems, and product-team effectiveness without confusing enablement with roadmap ownership.",
            "yes": ["launch coordination", "product feedback systems", "tooling and governance", "roadmap enablement", "product and engineering partnership"],
            "hesitations": ["generic project management without product-development fluency", "claiming product decisions that were only enabled"],
            "probes": ["launch readiness", "feedback routed into product decisions", "product process improvement", "tooling adoption"],
            "fail": "A process owner who cannot adapt operations to how product teams actually make and deliver decisions.",
        },
        "People Operations": {
            "problem": "Run trustworthy employee systems and programs while improving the experience of employees and managers.",
            "ideal": "A People/HR operator with direct domain depth, sound judgment, and practical systems experience.",
            "yes": ["employee lifecycle depth", "People systems and programs", "policy and compliance judgment", "manager enablement", "employee experience"],
            "hesitations": ["general team leadership presented as HR ownership", "missing direct experience in required People specialties"],
            "probes": ["employee lifecycle ownership", "People-system administration", "policy judgment", "manager and employee support"],
            "fail": "A strong general operator who lacks the HR-domain judgment required for sensitive employee work.",
        },
        "Chief of Staff": {
            "problem": "Increase an executive's leverage through synthesis, discretion, decision preparation, and priority follow-through.",
            "ideal": "A trusted executive operator with judgment, concise communication, discretion, and organizational influence.",
            "yes": ["executive decision preparation", "synthesis", "priority management", "operating cadence", "organizational influence"],
            "hesitations": ["project coordination without executive judgment", "verbosity or weak discretion"],
            "probes": ["a sensitive decision prepared", "competing executive priorities managed", "organizational influence without authority", "confidential work handled"],
            "fail": "A visible program manager who cannot exercise discretion or improve an executive's decisions and leverage.",
        },
    }
    model = common.get(archetype) or {
        "problem": str(interpretation.get("core_mission") or "Solve the concrete operating problem described in the posting."),
        "ideal": str(interpretation.get("candidate_profile") or "A candidate with direct functional evidence and credible execution judgment."),
        "yes": evidence_priorities(archetype)[:5],
        "hesitations": ["shared vocabulary without evidence of substantive ownership", "unclear fit against the role's true must-haves"],
        "probes": list(interpretation.get("major_fit_questions") or [])[:4],
        "fail": "A candidate whose keywords match but whose examples do not demonstrate the role's actual work.",
    }
    non_negotiables = [f"The posting explicitly requires: {value}." for value in explicit]
    inferred_yes = [f"The hiring manager is likely to care about {value}." for value in model["yes"]]
    confidence = float(interpretation.get("interpretation_confidence") or interpretation.get("confidence") or 0.5)
    alignment_matrix = list(alignment_matrix or [])
    gap_analysis = dict(gap_analysis or {})
    return {
        "archetype": archetype,
        "hiring_problem": model["problem"],
        "ideal_candidate_summary": model["ideal"],
        "likely_yes_factors": inferred_yes,
        "likely_hesitations": [f"The hiring manager may hesitate if there is {value}." for value in model["hesitations"]],
        "non_negotiables": non_negotiables,
        "preferred_or_trainable": [f"The posting presents as preferred or learnable: {value}." for value in interpretation.get("preferred_or_trainable") or []],
        "first_scan_priorities": _dedupe([*explicit[:3], *model["yes"][:4]]),
        "interview_probe_areas": [f"The hiring manager is likely to probe {value}." for value in model["probes"]],
        "likely_rejection_reasons": [model["fail"]],
        "application_proof_requirements": _dedupe([*explicit[:3], *model["yes"][:4]]),
        "application_positioning_risks": list(model["hesitations"]),
        "requirement_alignment": alignment_matrix,
        "evidence_status": {
            "missing_resume_language": list(gap_analysis.get("missing_because_not_on_resume") or []),
            "needs_confirmation": list(gap_analysis.get("missing_because_needs_confirmation") or []),
            "unsupported": list(gap_analysis.get("missing_because_unsupported") or []),
            "truly_absent": list(gap_analysis.get("missing_because_truly_absent") or []),
        },
        "profile_evidence_consulted": bool(alignment_matrix or gap_analysis),
        "confidence": round(confidence, 2),
        "inferred_notes": [
            "Hiring-manager priorities are inferred from the confirmed interpretation unless explicitly labeled as posting requirements.",
            *list(interpretation.get("interpretation_notes") or []),
        ],
    }


def build_application_strategy(
    interpretation: dict[str, Any],
    hiring_lens: dict[str, Any],
    match_report: dict[str, Any] | None = None,
    evidence_cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create the source-of-truth positioning plan used by every package material."""
    match_report = dict(match_report or {})
    assessment = dict(match_report.get("interpretation_assessment") or {})
    alignment_matrix = list(
        (match_report.get("capability_graph") or {}).get("alignment_matrix")
        or assessment.get("capability_alignment_matrix")
        or []
    )
    cards = list(evidence_cards or [])
    archetype = str(interpretation.get("primary_archetype") or "General Business Operations")
    selected_proof = [
        str(point)
        for card in cards
        for point in card.get("proof_points", [])[:1]
        if str(point).strip()
    ]
    direct_rows = [row for row in alignment_matrix if row.get("alignment_level") == "Direct"]
    adjacent_rows = [
        row for row in alignment_matrix
        if row.get("alignment_level") in {"Strong Adjacent", "Transferable"}
    ]
    direct = _dedupe(
        [
            *(assessment.get("directly_relevant_evidence") or []),
            *(title for row in direct_rows for title in row.get("supporting_evidence") or []),
        ]
    )
    adjacent = _dedupe(
        [
            *(assessment.get("adjacent_relevance") or []),
            *(title for row in adjacent_rows for title in row.get("supporting_evidence") or []),
            *selected_proof,
        ]
    )
    if archetype in TECHNICAL_ARCHETYPES:
        honest_boundary = (
            "Do not present general operations as a substitute for the role's technical function. Present technical ad operations, platform implementation support, measurement, QA, troubleshooting, and campaign reliability as direct evidence. Position formal Technical Solutions-function ownership as adjacent, and do not claim software engineering or API development."
        )
        must_not_claim = list(UNSUPPORTED_TECHNICAL_CLAIMS)
        thesis = (
            "Trisha brings direct technical ad-operations and implementation leadership, strong advertiser-platform and troubleshooting experience, and adjacent Technical Solutions leadership grounded in measurement readiness and campaign reliability."
        )
        interview_positioning = (
            "Lead with verified CM360, DV360, conversion tracking, server-to-server Conversion API implementation support, measurement, QA, and troubleshooting examples. Keep API development and formal Solutions Engineer management outside the claim."
        )
    else:
        honest_boundary = "Distinguish direct ownership from adjacent enablement and keep every claim within the stored evidence profile."
        must_not_claim = []
        thesis = f"Connect Trisha's strongest evidence to the role's actual {archetype.lower()} mission without broadening the claim beyond the work performed."
        interview_positioning = "Use specific decisions, actions, and results that map to the hiring manager's stated and inferred priorities."
    matrix_gaps = [
        str(row.get("remaining_gap") or "")
        for row in alignment_matrix
        if row.get("remaining_gap")
    ]
    material_gaps = _dedupe([*(match_report.get("material_fit_gaps") or []), *matrix_gaps])
    confirmed = interpretation.get("primary_interpretation") or {
        "archetype": archetype,
        "plain_english_description": interpretation.get("plain_english_summary"),
    }
    strategy_confidence = min(
        float(interpretation.get("interpretation_confidence") or 0.5),
        0.9 if cards else 0.6,
    )
    return {
        "confirmed_role_interpretation": confirmed,
        "interpretation_confirmed_by_user": bool(interpretation.get("user_reviewed")),
        "strategy_basis": "confirmed interpretation" if interpretation.get("user_reviewed") else "unconfirmed primary interpretation",
        "primary_hiring_problem": hiring_lens.get("hiring_problem"),
        "candidate_positioning": thesis,
        "strongest_direct_evidence": direct,
        "strongest_adjacent_evidence": adjacent[:6],
        "alignment_matrix": alignment_matrix,
        "evidence_gap_analysis": dict(match_report.get("evidence_gap_analysis") or {}),
        "material_gaps": material_gaps,
        "honest_boundary": honest_boundary,
        "must_prove": list(hiring_lens.get("application_proof_requirements") or [])[:6],
        "must_not_claim": must_not_claim,
        "resume_emphasis": evidence_priorities(archetype),
        "cover_letter_thesis": thesis,
        "cover_letter_proof_sequence": _dedupe([*direct, *adjacent])[:5],
        "interview_positioning": interview_positioning,
        "application_recommendation": match_report.get("recommended_action") or "Review First",
        "strategy_confidence": round(strategy_confidence, 2),
        "unconfirmed_interpretation_warning": (
            "Package strategy is based on an unconfirmed interpretation. Review the alternate interpretations and material questions before submitting."
            if not interpretation.get("user_reviewed")
            and interpretation.get("ambiguity_level") in {"Medium", "High"}
            else ""
        ),
        "evidence_selected": [str(card.get("id")) for card in cards],
        "evidence_rejected": [
            str(row.get("requirement"))
            for row in alignment_matrix
            if row.get("alignment_level") == "Unsupported"
        ],
    }


def interview_preparation_model(
    interpretation: dict[str, Any],
    hiring_lens: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    probes = list(hiring_lens.get("interview_probe_areas") or [])
    questions = list(interpretation.get("major_fit_questions") or [])
    examples = _dedupe(
        [
            *strategy.get("strongest_direct_evidence", []),
            *strategy.get("strongest_adjacent_evidence", []),
        ]
    )[:5]
    return {
        "likely_first_interview_question": (
            f"What experience best prepares you to solve this problem: {hiring_lens.get('hiring_problem', '').rstrip('.')}?"
        ),
        "likely_technical_or_functional_probe": probes[0] if probes else "Expect a detailed probe into the role's primary function.",
        "likely_candidate_concern": (hiring_lens.get("likely_hesitations") or ["The hiring manager may test whether the experience is direct or adjacent."])[0],
        "strongest_response_strategy": strategy.get("interview_positioning"),
        "examples_to_prepare": examples,
        "questions_to_clarify_role": questions[:5],
    }


def role_specificity_check(
    content: str,
    interpretation: dict[str, Any],
    hiring_lens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect generic-operations fallback and interpretation/package mismatch."""
    lowered = str(content or "").lower()
    archetype = str(interpretation.get("primary_archetype") or "General Business Operations")
    markers = ROLE_LANGUAGE.get(archetype, ())
    specific_hits = [marker for marker in markers if marker in lowered]
    generic_hits = [phrase for phrase in GENERIC_OPERATIONS_FALLBACK if phrase in lowered]
    role_specificity_score = min(100, 15 + (14 * len(specific_hits)))
    if archetype not in OPERATIONS_ARCHETYPES:
        role_specificity_score -= max(0, len(generic_hits) - len(specific_hits)) * 12
    role_specificity_score = max(0, role_specificity_score)
    unsupported = _unsupported_assertions(lowered)
    generic_fallback = bool(
        archetype not in OPERATIONS_ARCHETYPES
        and len(generic_hits) >= 3
        and len(specific_hits) < 3
    )
    minimum_specific = 3 if archetype in TECHNICAL_ARCHETYPES else (1 if markers else 0)
    mismatch = bool(markers) and len(specific_hits) < minimum_specific
    valid = not unsupported and not generic_fallback and not mismatch
    return {
        "valid": valid,
        "archetype": archetype,
        "role_specificity_score": role_specificity_score,
        "role_specific_signals": specific_hits,
        "generic_operations_signals": generic_hits,
        "generic_operations_fallback_warning": generic_fallback,
        "unsupported_claims_blocked": unsupported,
        "interpretation_package_consistent": not mismatch,
        "hiring_problem_addressed": bool(
            hiring_lens and any(
                token in lowered
                for token in re.findall(r"[a-z]{5,}", str(hiring_lens.get("hiring_problem") or "").lower())
            )
        ),
        "failure_reasons": _dedupe(
            [
                "The material lacks enough role-specific functional language."
                if mismatch else "",
                "Generic operations language dominates a non-operations interpretation."
                if generic_fallback else "",
                "Unsupported technical ownership appears in the material."
                if unsupported else "",
            ]
        ),
    }
