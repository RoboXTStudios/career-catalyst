"""Derive reviewable capabilities and requirement alignment from career evidence."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

try:
    from .evidence_profile import load_evidence_profile, select_profile_evidence
except ImportError:
    from evidence_profile import load_evidence_profile, select_profile_evidence


CAPABILITY_GRAPH_PATH = "data/capability_graph.yml"
SCHEMA_VERSION = 1
DERIVATION_TYPES = {
    "Directly Demonstrated", "Strongly Supported", "Transferable", "Emerging",
    "Needs Confirmation", "Unsupported",
}
ALIGNMENT_VALUES = {"Direct", "Strong Adjacent", "Transferable", "Weak", "Unsupported"}
ALIGNMENT_WEIGHTS = {
    "Direct": 1.0,
    "Strong Adjacent": 0.82,
    "Transferable": 0.58,
    "Weak": 0.25,
    "Unsupported": 0.0,
}
HARD_GATE_TERMS = (
    "employment law", "employment compliance", "benefits administration", "benefits",
    "hris ownership", "hris administration", "hris", "people policy",
    "employee relations investigation", "employee relations", "performance management",
    "software engineering", "software engineer",
    "api development", "develop apis", "coding", "licensed accounting", "cpa required",
    "clinical", "legal practice", "bar admission", "advanced data science",
    "machine learning engineering", "model training", "fine-tuning", "fine tuning",
    "mlops", "cloud architecture", "production api engineering", "full-stack", "full stack",
)
STRONG_PREFERENCE_TERMS = ("required", "must have", "minimum", "years of experience", "expertise")
LEARNABLE_TERMS = ("preferred", "nice to have", "a plus", "familiarity", "willing to learn")


CAPABILITY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "people_leadership": {
        "name": "People Leadership", "category": "People Leadership",
        "evidence": ["people_leadership", "campaign_operations_leadership"],
        "archetypes": ["People Operations", "General Business Operations", "Technical Solutions / Solutions Consulting"],
        "functions": ["team leadership", "coaching", "performance enablement"],
        "positioning": "Brought substantial people-leadership experience leading campaign operations practitioners.",
        "limitations": ["Do not relabel campaign operations leadership as formal HR administration or Solutions Engineering management."],
    },
    "technical_business_translation": {
        "name": "Technical Business Translation", "category": "Technical Business Translation",
        "evidence": ["cross_functional_technical_translation", "google_youtube_platforms", "advertising_technology"],
        "archetypes": ["Technical Solutions / Solutions Consulting", "Advertising Technology / Ad Operations", "Product Operations"],
        "functions": ["technical translation", "stakeholder communication", "platform enablement"],
        "positioning": "Translated technical platform requirements into operational guidance and advertiser delivery.",
        "limitations": ["Translation and operational application do not establish software engineering ownership."],
    },
    "operational_reliability": {
        "name": "Operational Reliability", "category": "Operational Reliability",
        "evidence": ["qa", "launch_readiness", "measurement_readiness", "technical_troubleshooting"],
        "archetypes": ["Technical Solutions / Solutions Consulting", "Advertising Technology / Ad Operations", "Program / Project Management"],
        "functions": ["reliability", "readiness", "quality", "issue resolution"],
        "positioning": "Built the validation, readiness, and escalation practices that kept campaign delivery reliable.",
        "limitations": [],
    },
    "technical_troubleshooting": {
        "name": "Technical Troubleshooting", "category": "Technical Troubleshooting",
        "evidence": ["technical_troubleshooting", "conversion_tracking", "qa"],
        "archetypes": ["Technical Solutions / Solutions Consulting", "Advertising Technology / Ad Operations"],
        "functions": ["troubleshooting", "diagnosis", "escalation management"],
        "positioning": "Diagnosed and coordinated resolution of campaign, trafficking, reporting, measurement, and platform issues.",
        "limitations": ["Does not establish code debugging or software engineering."],
    },
    "implementation_leadership": {
        "name": "Implementation Leadership", "category": "Implementation Leadership",
        "evidence": ["cm360", "dv360", "conversion_tracking", "server_to_server_conversion_api", "launch_readiness"],
        "archetypes": ["Implementation / Onboarding", "Technical Solutions / Solutions Consulting", "Advertising Technology / Ad Operations"],
        "functions": ["implementation", "operationalization", "launch readiness"],
        "positioning": "Led the business-side implementation support, validation, and operationalization of advertising-platform workflows.",
        "limitations": ["Implementation support does not mean API development, SDK engineering, or solution architecture ownership."],
    },
    "program_leadership": {
        "name": "Program Leadership", "category": "Program Leadership",
        "evidence": ["campaign_operations_leadership", "workflow_design", "launch_readiness"],
        "archetypes": ["Program / Project Management", "Strategic Operations", "Technical Program Management"],
        "functions": ["program delivery", "planning", "execution leadership"],
        "positioning": "Led complex campaign programs across multiple disciplines and delivery dependencies.",
        "limitations": [],
    },
    "cross_functional_leadership": {
        "name": "Cross-functional Leadership", "category": "Cross-functional Leadership",
        "evidence": ["campaign_operations_leadership", "cross_functional_technical_translation", "workflow_design"],
        "archetypes": ["Strategic Operations", "Chief of Staff", "Product Operations", "Technical Solutions / Solutions Consulting"],
        "functions": ["stakeholder influence", "coordination", "execution leadership"],
        "positioning": "Partnered across creative, media, analytics, technology, operations, and leadership stakeholders.",
        "limitations": [],
    },
    "process_design": {
        "name": "Process Design", "category": "Process Design",
        "evidence": ["workflow_design", "qa", "launch_readiness"],
        "archetypes": ["Strategic Operations", "Product Operations", "Transformation / Operational Excellence"],
        "functions": ["workflow design", "implementation standards", "handoffs"],
        "positioning": "Designed scalable workflows, handoffs, and implementation standards for complex campaign operations.",
        "limitations": [],
    },
    "governance": {
        "name": "Governance", "category": "Governance",
        "evidence": ["workflow_design", "qa", "campaign_operations_leadership"],
        "archetypes": ["Strategic Operations", "Chief of Staff", "Transformation / Operational Excellence"],
        "functions": ["governance", "standards", "accountability"],
        "positioning": "Created practical standards and controls that improved consistency without substituting process for judgment.",
        "limitations": [],
    },
    "risk_management": {
        "name": "Risk Management", "category": "Risk Management",
        "evidence": ["qa", "launch_readiness", "technical_troubleshooting", "measurement_readiness"],
        "archetypes": ["Program / Project Management", "Technical Solutions / Solutions Consulting", "Transformation / Operational Excellence"],
        "functions": ["risk visibility", "escalation", "quality controls"],
        "positioning": "Used validation, quality controls, and escalation procedures to surface delivery risk early.",
        "limitations": [],
    },
    "quality_assurance": {
        "name": "Quality Assurance", "category": "Quality Assurance",
        "evidence": ["qa", "measurement_readiness", "conversion_tracking"],
        "archetypes": ["Advertising Technology / Ad Operations", "Technical Solutions / Solutions Consulting", "Program / Project Management"],
        "functions": ["QA", "validation", "quality controls"],
        "positioning": "Developed QA standards and implementation-validation practices supporting reliable campaign outcomes.",
        "limitations": [],
    },
    "measurement_readiness": {
        "name": "Measurement Readiness", "category": "Measurement Readiness",
        "evidence": ["measurement_readiness", "conversion_tracking", "server_to_server_conversion_api"],
        "archetypes": ["Advertising Technology / Ad Operations", "Technical Solutions / Solutions Consulting", "Marketing Technology"],
        "functions": ["measurement", "tracking", "reporting readiness"],
        "positioning": "Led measurement readiness, tracking quality, reporting alignment, and launch validation.",
        "limitations": ["Do not convert operational measurement leadership into data-science or engineering claims."],
    },
    "platform_operations": {
        "name": "Platform Operations", "category": "Platform Operations",
        "evidence": ["advertising_technology", "google_youtube_platforms", "cm360", "dv360"],
        "archetypes": ["Advertising Technology / Ad Operations", "Technical Solutions / Solutions Consulting", "Marketing Technology"],
        "functions": ["platform activation", "campaign implementation", "operational readiness"],
        "positioning": "Owned the operational application of advertising platforms across campaign activation, delivery, and measurement.",
        "limitations": ["Platform operations do not establish platform product ownership or engineering."],
    },
    "product_collaboration": {
        "name": "Product Collaboration", "category": "Product Collaboration",
        "evidence": ["cross_functional_technical_translation", "technical_troubleshooting", "advertising_technology"],
        "archetypes": ["Product Operations", "Technical Solutions / Solutions Consulting"],
        "functions": ["product feedback", "requirements translation", "issue patterns"],
        "positioning": "Brought platform requirements and recurring delivery issues into cross-functional problem-solving.",
        "limitations": ["Does not establish roadmap or feature-priority ownership."],
        "default_strength": "Strong Adjacent Experience",
        "default_derivation": "Strongly Supported",
    },
    "client_leadership": {
        "name": "Client Leadership", "category": "Client Leadership",
        "evidence": ["campaign_operations_leadership", "advertising_technology", "technical_troubleshooting"],
        "archetypes": ["Technical Solutions / Solutions Consulting", "Customer Success", "Advertising Technology / Ad Operations"],
        "functions": ["advertiser delivery", "issue resolution", "stakeholder trust"],
        "positioning": "Led advertiser delivery and stakeholder issue resolution in enterprise entertainment campaigns.",
        "limitations": ["Do not imply formal technical-sales ownership."],
        "default_strength": "Strong Adjacent Experience",
        "default_derivation": "Strongly Supported",
    },
    "organizational_design": {
        "name": "Organizational Design", "category": "Organizational Design",
        "evidence": ["people_leadership", "workflow_design", "campaign_operations_leadership"],
        "archetypes": ["People Operations", "General Business Operations", "Transformation / Operational Excellence"],
        "functions": ["team structure", "role clarity", "organizational systems"],
        "positioning": "Applied organizational-design capabilities through team structures, role clarity, workflows, and operating systems.",
        "limitations": ["No formal People-function organizational-design ownership is established."],
        "default_strength": "Strong Adjacent Experience",
        "default_derivation": "Strongly Supported",
    },
    "manager_coaching": {
        "name": "Manager Coaching", "category": "Manager Coaching",
        "evidence": ["people_leadership"],
        "archetypes": ["People Operations", "General Business Operations", "Technical Solutions / Solutions Consulting"],
        "functions": ["coaching", "feedback", "team development"],
        "positioning": "Brought practical coaching experience from leading campaign operations practitioners.",
        "limitations": ["Coaching occurred in an operating-leadership context, not as formal HR program ownership."],
        "default_strength": "Strong Adjacent Experience",
        "default_derivation": "Strongly Supported",
    },
    "stakeholder_influence": {
        "name": "Stakeholder Influence", "category": "Stakeholder Influence",
        "evidence": ["cross_functional_technical_translation", "campaign_operations_leadership", "workflow_design"],
        "archetypes": ["People Operations", "Strategic Operations", "Chief of Staff", "Product Operations"],
        "functions": ["influence", "alignment", "stakeholder communication"],
        "positioning": "Influenced multi-disciplinary stakeholders by translating requirements, risks, and delivery decisions.",
        "limitations": [],
    },
    "executive_communication": {
        "name": "Executive Communication", "category": "Executive Communication",
        "evidence": ["campaign_operations_leadership", "cross_functional_technical_translation"],
        "archetypes": ["People Operations", "Strategic Operations", "Chief of Staff"],
        "functions": ["leadership communication", "decision visibility", "risk communication"],
        "positioning": "Provided senior stakeholders with clear visibility into delivery, risks, and decisions.",
        "limitations": [],
    },
}


AI_CAPABILITY_DEFINITIONS: dict[str, tuple[str, list[str], str, list[str], str]] = {
    "ai_product_strategy": (
        "AI Product Strategy", ["career_catalyst_ai_product", "career_catalyst_product_vision"],
        "Defined the vision and strategic scope for an AI-enabled career intelligence product.",
        ["AI Product Owner", "Product Operations", "Strategic Operations"], "Direct Experience",
    ),
    "ai_product_ownership": (
        "AI Product Ownership", ["career_catalyst_ai_product", "career_catalyst_requirements_engineering", "career_catalyst_product_testing"],
        "Served as product owner for Career Catalyst across vision, requirements, evaluation, and release quality.",
        ["AI Product Owner", "Product Management", "Product Operations"], "Direct Experience",
    ),
    "ai_workflow_design": (
        "AI Workflow Design", ["career_catalyst_ai_product", "career_catalyst_ai_workflow_architecture", "career_catalyst_human_in_loop"],
        "Designed the reasoning, context, review, and generation workflow for a functioning AI-enabled product.",
        ["AI Product Owner", "Product Operations", "AI Operations"], "Direct Experience",
    ),
    "human_in_loop_system_design": (
        "Human-in-the-loop System Design", ["career_catalyst_human_in_loop", "career_catalyst_responsible_ai", "career_catalyst_ai_evaluation"],
        "Built review, confirmation, override, rejection, provenance, and confidence controls into AI workflows.",
        ["AI Product Owner", "Responsible AI", "AI Operations"], "Direct Experience",
    ),
    "prompt_engineering": (
        "Prompt Engineering", ["career_catalyst_codex_delivery", "career_catalyst_ai_evaluation", "career_catalyst_requirements_engineering"],
        "Used structured prompting, explicit constraints, and iterative evaluation to direct AI-assisted implementation.",
        ["AI Operations", "Applied AI Consulting", "AI Product Owner"], "Direct Experience",
    ),
    "context_engineering": (
        "Context Engineering", ["career_catalyst_ai_workflow_architecture", "career_catalyst_codex_delivery", "career_catalyst_human_in_loop"],
        "Designed structured context and source-of-truth handoffs across multi-stage AI reasoning workflows.",
        ["AI Operations", "AI Product Owner", "Product Operations"], "Direct Experience",
    ),
    "ai_evaluation": (
        "AI Evaluation", ["career_catalyst_ai_evaluation", "career_catalyst_failure_analysis", "career_catalyst_product_testing"],
        "Evaluated AI conclusions and generated outputs against real roles, acceptance criteria, and truthfulness rules.",
        ["AI Evaluation", "Responsible AI", "AI Product Operations"], "Direct Experience",
    ),
    "ai_quality_assurance": (
        "AI Quality Assurance", ["career_catalyst_ai_evaluation", "career_catalyst_product_testing", "career_catalyst_responsible_ai"],
        "Established regression, consistency, and unsupported-claim checks for AI-generated career intelligence.",
        ["AI Evaluation", "AI Operations", "Quality Assurance"], "Direct Experience",
    ),
    "requirements_engineering": (
        "Requirements Engineering", ["career_catalyst_requirements_engineering", "career_catalyst_codex_delivery", "career_catalyst_failure_analysis"],
        "Translated product needs and failures into scoped requirements, safeguards, acceptance criteria, and tests.",
        ["AI Product Owner", "Technical Program Management", "Product Management"], "Direct Experience",
    ),
    "product_requirements_definition": (
        "Product Requirements Definition", ["career_catalyst_product_vision", "career_catalyst_requirements_engineering"],
        "Defined product behavior, data models, workflows, constraints, and acceptance outcomes.",
        ["Product Management", "Product Operations", "AI Product Owner"], "Direct Experience",
    ),
    "user_acceptance_testing": (
        "User Acceptance Testing", ["career_catalyst_product_testing", "career_catalyst_ai_evaluation", "career_catalyst_software_delivery"],
        "Performed functional and qualitative acceptance testing across UI, scoring, state, and generated materials.",
        ["Product Operations", "Program / Project Management", "Quality Assurance"], "Direct Experience",
    ),
    "iterative_product_development": (
        "Iterative Product Development", ["career_catalyst_ai_product", "career_catalyst_requirements_engineering", "career_catalyst_codex_delivery", "career_catalyst_product_testing"],
        "Directed sprint-based iteration from product failure through requirements, implementation, testing, and review.",
        ["Product Management", "Product Operations", "Technical Program Management"], "Direct Experience",
    ),
    "ai_assisted_software_delivery": (
        "AI-assisted Software Delivery", ["career_catalyst_codex_delivery", "career_catalyst_software_delivery", "career_catalyst_product_testing"],
        "Directed AI-assisted implementation through Codex and participated in repository, test, and release workflows.",
        ["AI Program Management", "AI Operations", "Technical Program Management"], "Direct Experience",
    ),
    "responsible_ai": (
        "Responsible AI", ["career_catalyst_responsible_ai", "career_catalyst_human_in_loop", "career_catalyst_ai_evaluation"],
        "Designed truthfulness, evidence, adjacency, confidence, and unsupported-claim safeguards.",
        ["Responsible AI", "AI Product Owner", "AI Evaluation"], "Direct Experience",
    ),
    "evidence_provenance_design": (
        "Evidence and Provenance Design", ["career_catalyst_responsible_ai", "career_catalyst_human_in_loop", "career_catalyst_ai_workflow_architecture"],
        "Designed source attribution and evidence controls that keep AI conclusions auditable.",
        ["Responsible AI", "AI Operations", "Product Operations"], "Direct Experience",
    ),
    "confidence_verification_design": (
        "Confidence and Verification Design", ["career_catalyst_human_in_loop", "career_catalyst_responsible_ai", "career_catalyst_ai_workflow_architecture"],
        "Designed confidence, verification, user-override, and unsupported-evidence states.",
        ["Responsible AI", "AI Evaluation", "AI Product Owner"], "Direct Experience",
    ),
    "cross_functional_technical_translation_ai": (
        "Cross-functional Technical Translation", ["career_catalyst_requirements_engineering", "career_catalyst_codex_delivery", "career_catalyst_ai_workflow_architecture"],
        "Translated domain needs and product failures into implementation-ready technical requirements.",
        ["AI Product Owner", "Technical Program Management", "Applied AI Consulting"], "Direct Experience",
    ),
    "workflow_automation": (
        "Workflow Automation", ["career_catalyst_ai_product", "career_catalyst_ai_workflow_architecture", "career_catalyst_codex_delivery"],
        "Designed and delivered AI-enabled workflows that automate repeatable career-intelligence tasks with human review.",
        ["AI Operations", "Product Operations", "Transformation / Operational Excellence"], "Direct Experience",
    ),
    "product_operations_ai": (
        "Product Operations", ["career_catalyst_ai_product", "career_catalyst_product_testing", "career_catalyst_software_delivery"],
        "Connected product requirements, testing, state behavior, quality controls, and iterative delivery.",
        ["Product Operations", "AI Product Operations", "Program / Project Management"], "Direct Experience",
    ),
    "systems_thinking": (
        "Systems Thinking", ["career_catalyst_ai_workflow_architecture", "career_catalyst_failure_analysis", "career_catalyst_responsible_ai"],
        "Connected interpretation, evidence, scoring, generation, persistence, and quality as one product system.",
        ["Strategic Operations", "Product Operations", "AI Product Owner"], "Direct Experience",
    ),
    "technical_program_leadership_ai": (
        "Technical Program Leadership", ["career_catalyst_requirements_engineering", "career_catalyst_codex_delivery", "career_catalyst_software_delivery", "career_catalyst_product_testing"],
        "Directed scoped technical implementation through requirements, dependencies, testing, and release verification.",
        ["Technical Program Management", "AI Program Management", "Product Operations"], "Strong Adjacent Experience",
    ),
    "git_development_collaboration": (
        "Git-based Development Collaboration", ["career_catalyst_software_delivery", "career_catalyst_codex_delivery", "career_catalyst_product_testing"],
        "Participated in Git-based delivery through status review, selective staging, tests, commits, and push verification.",
        ["Technical Program Management", "AI Program Management", "Product Operations"], "Direct Experience",
    ),
}

for _capability_id, (
    _name, _evidence, _positioning, _archetypes, _strength
) in AI_CAPABILITY_DEFINITIONS.items():
    CAPABILITY_DEFINITIONS[_capability_id] = {
        "name": _name,
        "category": _name,
        "evidence": _evidence,
        "archetypes": _archetypes,
        "functions": [_name.lower()],
        "positioning": _positioning,
        "limitations": [
            "Does not establish machine-learning engineering, model training, full-stack engineering, MLOps, cloud architecture, or sole software-engineering ownership."
        ] if _name in {
            "AI Product Ownership", "AI Workflow Design", "AI-assisted Software Delivery",
            "Technical Program Leadership", "Git-based Development Collaboration",
        } else [],
        "default_strength": _strength,
        "default_derivation": (
            "Directly Demonstrated" if _strength == "Direct Experience" else "Strongly Supported"
        ),
    }


REQUIREMENT_CAPABILITY_SIGNALS: dict[str, tuple[str, ...]] = {
    "People Leadership": ("lead a team", "leads a team", "manage a team", "manages a team", "people leadership", "people management", "coach", "mentor", "develop"),
    "Talent Selection": ("interview", "select talent", "hiring", "recruit"),
    "Talent Development": ("develop employees", "development plans", "career development"),
    "Employee Retention": ("retention", "retain", "employee relationships"),
    "Manager Coaching": ("manager coaching", "coach managers", "manager enablement"),
    "Performance Management": ("performance management", "performance concerns", "performance improvement"),
    "Employee Relations": ("employee relations", "workplace investigation", "employee investigation"),
    "HRIS Administration": ("hris", "human resources information system"),
    "Benefits Administration": ("benefits administration", "employee benefits", "benefits"),
    "Employment Compliance": ("employment law", "employment compliance", "labor law", "people policy"),
    "Organizational Design": ("organizational design", "organization design", "operating model"),
    "Stakeholder Influence": ("stakeholder", "influence", "partner teams", "aligning partner"),
    "Executive Communication": ("senior leadership", "executive communication", "leadership updates", "executive updates"),
    "Technical Business Translation": ("translate technical", "technical requirements", "business outcomes", "nontechnical"),
    "Operational Reliability": ("reliability", "service level", "launch readiness", "operational readiness"),
    "Technical Troubleshooting": ("troubleshoot", "diagnostic", "technical blocker", "technical issue", "debug"),
    "Implementation Leadership": ("implementation", "integration", "configure", "go live", "pixel", "conversions api"),
    "Cross-functional Leadership": ("cross-functional", "product and engineering", "sales, product", "influence"),
    "Process Design": ("process design", "workflow", "handoff", "operating process"),
    "Governance": ("governance", "standards", "controls"),
    "Risk Management": ("risk", "escalation", "constraints"),
    "Quality Assurance": ("quality assurance", "qa", "validation", "quality control"),
    "Measurement Readiness": ("measurement", "tracking", "signal", "reporting alignment"),
    "Platform Operations": ("platform activation", "campaign delivery", "ad tech", "adtech", "programmatic"),
    "Product Collaboration": ("product feedback", "product development", "product and engineering"),
    "Client Leadership": ("client", "customer", "advertiser", "escalation"),
    "AI Product Strategy": ("ai product strategy", "ai product vision", "ai strategy"),
    "AI Product Ownership": ("ai product owner", "own ai products", "ai product management"),
    "AI Workflow Design": ("ai workflow", "llm workflow", "reasoning workflow"),
    "Human-in-the-loop System Design": ("human-in-the-loop", "human in the loop", "human review"),
    "Prompt Engineering": ("prompt engineering", "prompt design", "prompt evaluation"),
    "Context Engineering": ("context engineering", "context design", "context management"),
    "AI Evaluation": ("ai evaluation", "llm evaluation", "evaluate ai"),
    "AI Quality Assurance": ("ai quality", "ai qa", "hallucination prevention"),
    "Requirements Engineering": ("requirements engineering", "acceptance criteria", "product requirements"),
    "User Acceptance Testing": ("user acceptance testing", "uat", "acceptance testing"),
    "Responsible AI": ("responsible ai", "ai safety", "ai truthfulness"),
    "Workflow Automation": ("workflow automation", "automate workflows", "automation strategy"),
    "Systems Thinking": ("systems thinking", "system design"),
    "Technical Program Leadership": ("technical program", "technical delivery", "implementation program"),
    "Git-based Development Collaboration": ("git", "github", "version control"),
    "Software Engineering": ("software engineering", "software engineer", "coding", "codebase"),
    "API Development": ("api development", "develop apis", "production apis", "production api"),
    "Machine Learning Engineering": ("machine learning engineering", "model training", "fine tuning", "fine-tuning"),
    "MLOps": ("mlops", "model deployment"),
    "Cloud Architecture": ("cloud architecture", "cloud architect"),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _normalize_capability(item: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    result.setdefault("description", f"Demonstrated capability in {result.get('name', 'this area')}.")
    result.setdefault("strength", "Transferable Capability")
    result.setdefault("confidence", "Medium")
    result.setdefault("derivation_type", "Transferable")
    for field in (
        "supporting_evidence_ids", "contradicting_evidence_ids", "related_capabilities",
        "applicable_role_archetypes", "applicable_functions", "applicable_industries",
        "limitations", "applications_used",
    ):
        result[field] = _dedupe(result.get(field) or [])
    result.setdefault("technical_depth", "Not specified")
    result.setdefault("leadership_depth", "Not specified")
    result.setdefault("people_scope", "Not specified")
    result.setdefault("customer_scope", "Not specified")
    result.setdefault("recommended_positioning", "Use the strongest truthful evidence and preserve ownership boundaries.")
    result.setdefault("user_review_status", "Derived")
    result.setdefault("created_at", _now())
    result.setdefault("updated_at", result["created_at"])
    return result


def derive_capabilities(
    evidence_profile: dict[str, Any], reviews: Optional[dict[str, dict[str, Any]]] = None
) -> list[dict[str, Any]]:
    """Derive capabilities from facts without silently user-confirming them."""
    evidence_by_id = {
        str(item.get("id")): item for item in evidence_profile.get("evidence") or []
    }
    reviews = dict(reviews or {})
    capabilities = []
    for capability_id, definition in CAPABILITY_DEFINITIONS.items():
        supporting_ids = [
            evidence_id for evidence_id in definition["evidence"]
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].get("verification_status") in {"Verified", "User Confirmed"}
        ]
        if not supporting_ids:
            continue
        support = [evidence_by_id[evidence_id] for evidence_id in supporting_ids]
        high_count = sum(item.get("confidence") == "High" for item in support)
        confidence = "High" if high_count >= 2 else "Medium"
        strength = definition.get("default_strength") or (
            "Direct Experience" if any(
                item.get("evidence_type") in {"Direct Experience", "User Confirmed", "Resume Verified"}
                for item in support
            ) else "Strong Adjacent Experience"
        )
        derivation = definition.get("default_derivation") or (
            "Directly Demonstrated" if strength == "Direct Experience" else "Strongly Supported"
        )
        capability = _normalize_capability(
            {
                "id": capability_id,
                "name": definition["name"],
                "description": f"Derived from {len(supporting_ids)} verified career evidence item(s).",
                "category": definition["category"],
                "strength": strength,
                "confidence": confidence,
                "derivation_type": derivation,
                "supporting_evidence_ids": supporting_ids,
                "contradicting_evidence_ids": [],
                "related_capabilities": [],
                "applicable_role_archetypes": definition["archetypes"],
                "applicable_functions": definition["functions"],
                "applicable_industries": _dedupe(
                    industry for item in support for industry in item.get("industries") or []
                ),
                "technical_depth": max(
                    (str(item.get("technical_depth") or "Not specified") for item in support),
                    key=lambda value: {"High": 3, "Moderate": 2, "Low": 1, "Not specified": 0}.get(value, 0),
                ),
                "leadership_depth": max(
                    (str(item.get("leadership_scope") or "Not specified") for item in support),
                    key=len,
                ),
                "people_scope": max(
                    (str(item.get("people_management") or "Not specified") for item in support),
                    key=len,
                ),
                "customer_scope": max(
                    (str(item.get("customer_facing") or "Not specified") for item in support),
                    key=len,
                ),
                "recommended_positioning": definition["positioning"],
                "limitations": definition["limitations"],
            }
        )
        review = dict(reviews.get(capability_id) or {})
        if review:
            for field in (
                "name", "description", "strength", "confidence", "recommended_positioning",
                "technical_depth", "leadership_depth", "people_scope", "customer_scope",
                "user_review_status",
            ):
                if review.get(field) not in (None, ""):
                    capability[field] = review[field]
            capability["limitations"] = _dedupe(
                [*capability["limitations"], *(review.get("limitations") or [])]
            )
            capability["supporting_evidence_ids"] = _dedupe(
                [*capability["supporting_evidence_ids"], *(review.get("supporting_evidence_ids") or [])]
            )
            capability["updated_at"] = review.get("updated_at") or _now()
        if capability.get("user_review_status") != "Rejected":
            capabilities.append(capability)
    return capabilities


def load_capability_graph(
    project_root: str | Path | None = None,
    evidence_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / CAPABILITY_GRAPH_PATH
    stored: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            stored = loaded
    reviews = {
        str(item.get("id")): dict(item)
        for item in stored.get("capability_reviews") or []
        if isinstance(item, dict) and item.get("id")
    }
    profile = evidence_profile or load_evidence_profile(root)
    capabilities = derive_capabilities(profile, reviews)
    return {
        "schema_version": SCHEMA_VERSION,
        "graph_updated_at": stored.get("graph_updated_at") or _now(),
        "capabilities": capabilities,
        "capability_reviews": list(reviews.values()),
        "alignment_weights": dict(stored.get("alignment_weights") or ALIGNMENT_WEIGHTS),
    }


def save_capability_review(
    capability_id: str,
    updates: dict[str, Any],
    project_root: str | Path | None = None,
) -> Path:
    """Persist explicit capability review without converting other derived capabilities."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / CAPABILITY_GRAPH_PATH
    stored = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    stored = dict(stored or {})
    reviews = [dict(item) for item in stored.get("capability_reviews") or []]
    existing = next((item for item in reviews if item.get("id") == capability_id), None)
    values = {"id": capability_id, **dict(updates), "updated_at": _now()}
    if existing is None:
        reviews.append(values)
    else:
        existing.update(values)
    stored.update(
        {
            "schema_version": SCHEMA_VERSION,
            "graph_updated_at": _now(),
            "alignment_weights": dict(stored.get("alignment_weights") or ALIGNMENT_WEIGHTS),
            "capability_reviews": reviews,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(stored, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    # Capability review is an explicit mutation, so updating the lightweight aggregate is safe.
    try:
        from .evidence_summary import refresh_evidence_page_summary
    except ImportError:
        from evidence_summary import refresh_evidence_page_summary

    refresh_evidence_page_summary(root)
    return path


def classify_requirement(requirement: str) -> str:
    lowered = requirement.lower()
    if any(term in lowered for term in HARD_GATE_TERMS):
        return "Hard Gate"
    if any(term in lowered for term in LEARNABLE_TERMS):
        return "Learnable Requirement"
    if any(term in lowered for term in STRONG_PREFERENCE_TERMS):
        return "Strong Preference"
    if any(term in lowered for term in ("results-oriented", "fast-paced", "strategic thinker", "cross-functional")) and len(lowered.split()) < 12:
        return "Cosmetic Keyword"
    return "Contextual Requirement"


def requirement_capabilities(requirement: str) -> list[str]:
    lowered = requirement.lower()
    return [
        name for name, signals in REQUIREMENT_CAPABILITY_SIGNALS.items()
        if any(
            (
                bool(re.search(rf"\b{re.escape(signal)}\b", lowered))
                if " " not in signal else signal in lowered
            )
            for signal in signals
        )
    ]


def _alignment_for_capabilities(
    required_capabilities: list[str], capabilities: list[dict[str, Any]], requirement_type: str
) -> tuple[str, list[dict[str, Any]]]:
    matching = [
        capability for capability in capabilities
        if capability.get("name") in required_capabilities
    ]
    if not matching:
        return "Unsupported", []
    rank = {
        "Direct Experience": "Direct",
        "Strong Adjacent Experience": "Strong Adjacent",
        "Transferable Capability": "Transferable",
        "Emerging": "Weak",
        "Unsupported": "Unsupported",
    }
    best = max(
        (rank.get(str(item.get("strength")), "Weak") for item in matching),
        key=lambda value: ALIGNMENT_WEIGHTS[value],
    )
    if requirement_type == "Hard Gate":
        matched_names = {str(item.get("name")) for item in matching}
        every_required_capability_is_direct = (
            set(required_capabilities) <= matched_names
            and all(rank.get(str(item.get("strength"))) == "Direct" for item in matching)
        )
        if not every_required_capability_is_direct:
            return "Unsupported", matching
    return best, matching


def build_alignment_matrix(
    requirements: Iterable[Any],
    capability_graph: dict[str, Any],
    evidence_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Decompose requirements and preserve direct, adjacent, transferable, and unsupported levels."""
    capabilities = list(capability_graph.get("capabilities") or [])
    rows = []
    for raw in requirements:
        requirement = str(raw.get("requirement") if isinstance(raw, dict) else raw).strip()
        if not requirement:
            continue
        lowered_requirement = requirement.lower()
        if requirement.startswith("#"):
            continue
        if any(
            signal in lowered_requirement
            for signal in ("<a ", "href=", "for more information, visit", "http://", "https://")
        ):
            continue
        requirement_type = classify_requirement(requirement)
        underlying = requirement_capabilities(requirement)
        alignment, matching = _alignment_for_capabilities(
            underlying, capabilities, requirement_type
        )
        people_function_context = any(
            signal in requirement.lower()
            for signal in (
                "people operations", "human resources", "hr team", "people team",
                "people leadership",
            )
        )
        context_sensitive_people_capabilities = {
            "People Leadership", "Manager Coaching", "Organizational Design",
        }
        if (
            alignment == "Direct"
            and people_function_context
            and any(item.get("name") in context_sensitive_people_capabilities for item in matching)
        ):
            alignment = "Strong Adjacent"
        evidence_ids = _dedupe(
            evidence_id
            for capability in matching
            for evidence_id in capability.get("supporting_evidence_ids") or []
        )
        evidence_by_id = {
            str(item.get("id")): item for item in evidence_profile.get("evidence") or []
        }
        supporting = [
            evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id
        ]
        hard = requirement_type == "Hard Gate"
        remaining_gap = ""
        if alignment == "Unsupported":
            remaining_gap = "Direct evidence is required and is not established."
        elif alignment == "Strong Adjacent":
            remaining_gap = "The underlying capability is strong, but the exact function or formal ownership differs."
        elif alignment == "Transferable":
            remaining_gap = "The capability is demonstrated in another function or context; role-specific depth remains to verify."
        positioning = (
            matching[0].get("recommended_positioning")
            if matching
            else "Do not claim this requirement without new verified evidence."
        )
        rows.append(
            {
                "requirement": requirement,
                "exact_task_or_responsibility": requirement,
                "underlying_capabilities": underlying,
                "required_depth": "Direct evidence required" if hard else "Role-appropriate depth",
                "required_context": "Domain-specific" if hard else "Context may be adjacent when outcomes and judgment are comparable",
                "required_proof": "Verified or user-confirmed evidence",
                "domain_specific_experience_mandatory": hard,
                "adjacent_experience_acceptable": not hard,
                "transferable_capability_acceptable": not hard and requirement_type != "Strong Preference",
                "requirement_type": requirement_type,
                "alignment_level": alignment,
                "supporting_evidence_ids": evidence_ids,
                "supporting_evidence": [item.get("title") for item in supporting],
                "derived_capabilities": [item.get("name") for item in matching],
                "remaining_gap": remaining_gap,
                "gap_types": _gap_types(requirement, alignment, remaining_gap),
                "application_positioning": positioning,
                "score_credit": ALIGNMENT_WEIGHTS[alignment],
            }
        )
    return rows


def _gap_types(requirement: str, alignment: str, remaining_gap: str) -> list[str]:
    if alignment == "Direct":
        return []
    lowered = requirement.lower()
    gaps = []
    if alignment in {"Strong Adjacent", "Transferable"}:
        gaps.append("Functional title missing")
        gaps.append("Transferable capability present")
    if any(term in lowered for term in ("hris", "tableau", "looker", "hex", "platform", "tool")):
        gaps.append("Tool knowledge missing" if alignment == "Unsupported" else "Tool knowledge needs verification")
    if any(term in lowered for term in ("own", "ownership", "lead", "manage")) and alignment != "Direct":
        gaps.append("Formal ownership missing")
    if alignment == "Unsupported":
        gaps.extend(["Exact experience missing", "Evidence truly absent"])
    if remaining_gap and not gaps:
        gaps.append("Industry context missing")
    return _dedupe(gaps)


def alignment_score(
    alignment_matrix: list[dict[str, Any]], weights: Optional[dict[str, float]] = None
) -> int:
    if not alignment_matrix:
        return 0
    configured = dict(ALIGNMENT_WEIGHTS)
    configured.update(weights or {})
    credits = [configured.get(str(row.get("alignment_level")), 0.0) for row in alignment_matrix]
    return round((sum(credits) / len(credits)) * 100)


def capability_explorer_summary(graph: dict[str, Any]) -> dict[str, Any]:
    capabilities = list(graph.get("capabilities") or [])
    return {
        "total_capabilities": len(capabilities),
        "direct": sum(item.get("strength") == "Direct Experience" for item in capabilities),
        "adjacent": sum(item.get("strength") == "Strong Adjacent Experience" for item in capabilities),
        "confirmed": sum(item.get("user_review_status") == "Confirmed" for item in capabilities),
        "capabilities": capabilities,
    }
