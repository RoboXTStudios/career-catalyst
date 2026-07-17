"""Functional role lenses, requirement mapping, and applicant-copy safeguards."""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

try:
    from .employer_identity import (
        employer_name_violations,
        normalize_applicant_employer_names,
    )
except ImportError:
    from employer_identity import employer_name_violations, normalize_applicant_employer_names


ROLE_LENSES = (
    "people_operations",
    "business_operations",
    "strategic_operations",
    "product_operations",
    "marketing_operations",
    "program_portfolio_management",
    "transformation_operational_excellence",
    "chief_of_staff_executive_operations",
    "creative_entertainment_operations",
    "organizational_effectiveness",
)

ROLE_LENS_LABELS = {
    "people_operations": "People Operations",
    "business_operations": "Business Operations",
    "strategic_operations": "Strategic Operations",
    "product_operations": "Product Operations",
    "marketing_operations": "Marketing Operations",
    "program_portfolio_management": "Program / Portfolio Management",
    "transformation_operational_excellence": "Transformation / Operational Excellence",
    "chief_of_staff_executive_operations": "Chief of Staff / Executive Operations",
    "creative_entertainment_operations": "Creative / Entertainment Operations",
    "organizational_effectiveness": "Organizational Effectiveness",
}

LENS_SIGNALS = {
    "people_operations": {
        "title": ("people operations", "people ops"),
        "description": (
            "people team",
            "people strategy",
            "people systems",
            "people programs",
            "employee life cycle",
            "employee lifecycle",
            "people operations specialists",
            "team efficacy",
            "coaching",
            "feedback",
            "people policies",
            "people data",
        ),
    },
    "business_operations": {
        "title": ("business operations", "operations director", "director of operations"),
        "description": (
            "business operations",
            "business functions",
            "operating cadence",
            "capacity planning",
            "operational reporting",
            "business outcomes",
        ),
    },
    "strategic_operations": {
        "title": ("strategic operations", "strategy and operations", "strategy operations"),
        "description": (
            "strategic priorities",
            "company strategy",
            "executive decisions",
            "business planning",
            "strategic initiatives",
            "decision support",
        ),
    },
    "product_operations": {
        "title": ("product operations", "product strategy", "product manager"),
        "description": (
            "product roadmap",
            "product lifecycle",
            "product adoption",
            "product requirements",
            "product feedback",
            "product and engineering",
            "user needs",
        ),
    },
    "marketing_operations": {
        "title": ("marketing operations", "campaign operations", "martech"),
        "description": (
            "marketing operations",
            "campaign execution",
            "marketing performance",
            "media planning",
            "brand marketing",
            "campaign measurement",
            "crm",
        ),
    },
    "program_portfolio_management": {
        "title": ("program manager", "portfolio", "pmo", "project manager"),
        "description": (
            "program management",
            "portfolio management",
            "project management",
            "milestones",
            "dependencies",
            "program governance",
            "resource planning",
        ),
    },
    "transformation_operational_excellence": {
        "title": ("transformation", "operational excellence", "continuous improvement"),
        "description": (
            "operational excellence",
            "continuous improvement",
            "transformation",
            "change adoption",
            "process improvement",
            "operating model",
        ),
    },
    "chief_of_staff_executive_operations": {
        "title": ("chief of staff", "executive operations"),
        "description": (
            "executive leadership",
            "leadership team",
            "executive priorities",
            "board",
            "decision cadence",
            "executive communication",
        ),
    },
    "creative_entertainment_operations": {
        "title": ("creative operations", "entertainment operations", "studio operations"),
        "description": (
            "creative teams",
            "entertainment",
            "content production",
            "franchise",
            "theatrical",
            "streaming",
            "creative assets",
        ),
    },
    "organizational_effectiveness": {
        "title": ("organizational effectiveness", "organizational development"),
        "description": (
            "organizational design",
            "organizational effectiveness",
            "team effectiveness",
            "team efficacy",
            "ways of working",
            "change management",
            "manager enablement",
        ),
    },
}

PEOPLE_OPERATIONS_UNSUPPORTED = {
    "human resources leadership": ("human resources leadership", "hr leadership", "hr leader"),
    "HR business partnering": ("hr business partner", "hrbp"),
    "employee relations": ("employee relations", "workplace investigations", "investigations"),
    "labor relations": ("labor relations", "collective bargaining"),
    "employment law": ("employment law", "legal compliance"),
    "benefits administration": ("benefits administration", "benefits programs"),
    "compensation": ("compensation", "payroll"),
    "talent acquisition": ("talent acquisition", "recruiting leadership"),
    "performance management ownership": ("performance management", "succession planning"),
    "workforce planning": ("workforce planning",),
    "organizational design": ("organizational design",),
    "HRIS ownership": ("hris", "workday administration", "workday"),
    "people analytics": ("people analytics", "people data"),
    "policy ownership": ("policy authorship", "people policies", "hr policies"),
    "employee lifecycle ownership": ("employee life cycle", "employee lifecycle"),
    "direct People Operations tenure": ("experience in a people operations role",),
    "people policy ownership": ("people programs policies", "people policies", "policies and processes"),
}

PEOPLE_OPERATIONS_SAFE_SIGNALS = {
    "cross-functional collaboration": (
        ("cross-functional", "stakeholder", "partner teams"),
        ("omg23_disney_leadership",),
        "cross-functional partnership and stakeholder listening",
    ),
    "workflow and process implementation": (
        ("workflow", "process", "systems", "continuous improvement"),
        ("governance_qa_delivery",),
        "repeatable workflows, usable standards, and practical implementation",
    ),
    "team leadership": (
        ("lead and develop", "lead a team", "team efficacy", "coaching", "feedback"),
        ("omg23_disney_leadership",),
        "team leadership and enabling people to work with clearer expectations",
    ),
    "change adoption": (
        ("change", "adoption", "implement", "optimize"),
        ("governance_qa_delivery",),
        "change adoption and operational consistency",
    ),
    "communication and reporting": (
        ("communication", "reports", "decks", "updates", "executive leadership"),
        ("omg23_disney_leadership", "multiverse_editorial"),
        "clear communication and decision-ready updates",
    ),
}

PEOPLE_OPERATIONS_OVERCLAIMS = (
    "led people operations",
    "people operations transformation",
    "human resources leader",
    "hr leader",
    "hr business partner",
    "owned employee relations",
    "led employee relations",
    "labor relations",
    "employment law",
    "benefits administration",
    "compensation strategy",
    "payroll",
    "talent acquisition leadership",
    "owned performance management",
    "succession planning",
    "workforce planning",
    "owned organizational design",
    "hris ownership",
    "workday administration",
    "people analytics leader",
    "authored hr policies",
    "owned the employee lifecycle",
)

PEOPLE_OPERATIONS_OFF_LENS = (
    "seller enablement",
    "product activation",
    "ad technology",
    "ad-tech",
    "adtech",
    "brand auction",
    "campaign measurement",
    "advertiser execution",
    "media-channel",
)

GENERIC_ADVISORY_PHRASES = (
    "form a clear hypothesis",
    "shape an operating model",
    "advisory thinking",
    "advisory mindset",
    "operator's fluency",
    "strategically sound",
    "transformation across its clients and business",
)


def _normalize(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _description_value(parsed_job: dict[str, Any]) -> str:
    direct = str(parsed_job.get("job_description") or "").strip()
    if direct:
        return direct
    raw = str(parsed_job.get("raw_text") or "")
    marker = re.search(r"^##\s+Job Description\s*$", raw, flags=re.I | re.M)
    return raw[marker.end() :].strip() if marker else raw


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        key = _normalize(clean)
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def classify_role_lens(parsed_job: dict[str, Any]) -> dict[str, Any]:
    """Classify function from title plus substantive posting signals."""
    title = _normalize(parsed_job.get("job_title") or parsed_job.get("title"))
    description = _normalize(_description_value(parsed_job))
    scores: dict[str, int] = {}
    supporting: dict[str, list[str]] = {}
    for lens, groups in LENS_SIGNALS.items():
        title_hits = [signal for signal in groups["title"] if _normalize(signal) in title]
        description_hits = [
            signal for signal in groups["description"] if _normalize(signal) in description
        ]
        if lens == "people_operations":
            anchored = bool(title_hits) or any(
                signal in description_hits
                for signal in (
                    "people team",
                    "people strategy",
                    "people systems",
                    "people programs",
                    "employee life cycle",
                    "employee lifecycle",
                    "people operations specialists",
                    "people data",
                )
            )
            if not anchored:
                description_hits = []
        scores[lens] = (2 * len(title_hits)) + (3 * len(description_hits))
        supporting[lens] = _dedupe((*title_hits, *description_hits))
    ranked = sorted(scores, key=lambda lens: (-scores[lens], ROLE_LENSES.index(lens)))
    primary = ranked[0] if scores[ranked[0]] > 0 else "business_operations"
    secondary = (
        "organizational_effectiveness"
        if primary == "people_operations"
        and scores["organizational_effectiveness"] >= 3
        else next(
            (lens for lens in ranked[1:] if scores[lens] >= max(3, scores[primary] // 3)),
            "",
        )
    )
    evidence_weight = min(1.0, scores[primary] / 18.0)
    confidence = round(0.45 + (0.5 * evidence_weight), 2)
    return {
        "primary": primary,
        "primary_label": ROLE_LENS_LABELS[primary],
        "secondary": secondary or None,
        "secondary_label": ROLE_LENS_LABELS.get(secondary) if secondary else None,
        "confidence": confidence,
        "confidence_label": "High" if confidence >= 0.8 else "Medium" if confidence >= 0.6 else "Low",
        "supporting_signals": supporting[primary],
        "secondary_signals": supporting.get(secondary, []) if secondary else [],
        "scores": scores,
    }


def _requirement_sentences(parsed_job: dict[str, Any]) -> list[str]:
    raw = _description_value(parsed_job)
    marker = re.search(r"^##\s+Job Description\s*$", raw, flags=re.I | re.M)
    if marker:
        raw = raw[marker.end() :]
    pieces = re.split(r"(?:\n+|(?<=[.!?])\s+|[·•])", raw)
    requirements = []
    for piece in pieces:
        clean = re.sub(r"\s+", " ", piece).strip(" -:;")
        if len(clean.split()) >= 5 and any(
            term in clean.lower()
            for term in (
                "lead",
                "manage",
                "design",
                "implement",
                "experience",
                "ability",
                "responsible",
                "gather",
                "translate",
                "collaborate",
                "develop",
                "strategy",
                "systems",
                "program",
                "operations",
            )
        ):
            requirements.append(clean)
    return _dedupe(requirements)[:16]


def build_requirement_map(
    parsed_job: dict[str, Any], role_lens: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Map major requirements to safe, verified evidence and vocabulary."""
    lens = role_lens or classify_role_lens(parsed_job)
    mapped: list[dict[str, Any]] = []
    for requirement in _requirement_sentences(parsed_job):
        lowered = requirement.lower()
        unsupported = [
            concept
            for concept, terms in PEOPLE_OPERATIONS_UNSUPPORTED.items()
            if any(term in lowered for term in terms)
        ] if lens["primary"] == "people_operations" else []
        safe_matches = [
            (concept, values)
            for concept, values in PEOPLE_OPERATIONS_SAFE_SIGNALS.items()
            if any(term in lowered for term in values[0])
        ] if lens["primary"] == "people_operations" else []
        if unsupported:
            strength = "Unsupported"
            evidence_ids: list[str] = []
            safe_vocabulary = [
                "operations background rather than ownership of this HR specialty"
            ]
        elif safe_matches:
            concepts = [concept for concept, _values in safe_matches]
            evidence_ids = _dedupe(
                evidence_id
                for _concept, values in safe_matches
                for evidence_id in values[1]
            )
            safe_vocabulary = _dedupe(values[2] for _concept, values in safe_matches)
            strength = (
                "Direct evidence"
                if concepts == ["cross-functional collaboration"]
                else "Adjacent evidence"
                if any(term in lowered for term in ("coaching", "developing", "feedback"))
                else "Strong transferable evidence"
            )
        elif lens["primary"] == "people_operations":
            strength = "Adjacent evidence"
            evidence_ids = ["governance_qa_delivery"]
            safe_vocabulary = ["adjacent operational experience, framed transparently"]
        else:
            strength = "Unknown"
            evidence_ids = []
            safe_vocabulary = []
        mapped.append(
            {
                "requirement": requirement,
                "normalized_concept": unsupported[0] if unsupported else _normalize(requirement)[:120],
                "strength": strength,
                "evidence_ids": evidence_ids,
                "safe_vocabulary": safe_vocabulary,
                "prohibited_overclaim_language": list(PEOPLE_OPERATIONS_OVERCLAIMS)
                if lens["primary"] == "people_operations"
                else [],
            }
        )
    return mapped


def role_lens_quality_violations(
    content: Any,
    role_lens: dict[str, Any],
    *,
    material_type: str = "material",
) -> list[dict[str, Any]]:
    """Return structured reasons when applicant copy disagrees with its role lens."""
    text = str(content or "")
    lowered = text.lower()
    violations = employer_name_violations(text)
    if role_lens.get("primary") != "people_operations":
        return violations
    for phrase in PEOPLE_OPERATIONS_OVERCLAIMS:
        if phrase in lowered:
            violations.append(
                {
                    "code": "unsupported_people_operations_claim",
                    "detail": phrase,
                    "correctable": False,
                }
            )
    off_lens_hits = [phrase for phrase in PEOPLE_OPERATIONS_OFF_LENS if phrase in lowered]
    if len(off_lens_hits) >= 2:
        violations.append(
            {
                "code": "people_operations_off_lens_vocabulary",
                "detail": off_lens_hits,
                "correctable": False,
            }
        )
    advisory_hits = [phrase for phrase in GENERIC_ADVISORY_PHRASES if phrase in lowered]
    if advisory_hits:
        violations.append(
            {
                "code": "generic_advisory_transformation_framing",
                "detail": advisory_hits,
                "correctable": False,
            }
        )
    repeated_proof = [
        phrase
        for phrase in (
            "led cross-functional teams",
            "introduced clearer workflows",
            "introduced scalable workflows",
            "operations rather than a traditional hr function",
        )
        if lowered.count(phrase) > 1
    ]
    if repeated_proof:
        violations.append(
            {
                "code": "repeated_people_operations_proof",
                "detail": repeated_proof,
                "correctable": False,
            }
        )
    people_signals = sum(
        phrase in lowered
        for phrase in (
            "how teams work",
            "people doing the work",
            "team",
            "manager",
            "communication",
            "ownership",
            "change",
            "day-to-day work",
            "people-centered",
        )
    )
    if material_type.lower() in {"cover_letter", "cover letter"} and people_signals < 3:
        violations.append(
            {
                "code": "generic_people_operations_letter",
                "detail": people_signals,
                "correctable": False,
            }
        )
    return violations


def enforce_role_lens_quality(
    content: str,
    role_lens: dict[str, Any],
    *,
    material_type: str = "material",
    rewrite: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Allow one controlled rewrite, then return structured pass/fail diagnostics."""
    normalized = normalize_applicant_employer_names(content)
    violations = role_lens_quality_violations(
        normalized, role_lens, material_type=material_type
    )
    attempted = False
    if violations and rewrite is not None:
        attempted = True
        normalized = normalize_applicant_employer_names(rewrite(normalized))
        violations = role_lens_quality_violations(
            normalized, role_lens, material_type=material_type
        )
    return normalized, {
        "valid": not violations,
        "violations": violations,
        "rewrite_attempted": attempted,
        "rewrite_succeeded": attempted and not violations,
    }
