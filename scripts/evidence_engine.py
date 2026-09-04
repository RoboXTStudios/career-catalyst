"""Evidence card loading and role-aware selection for generated materials."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

try:
    from .application_strategy import evidence_priorities
    from .evidence_profile import load_evidence_profile, select_profile_evidence
    from .human_positioning import evidence_capability_score
    from .role_editing import detect_role_editing_category
except ImportError:
    from application_strategy import evidence_priorities
    from evidence_profile import load_evidence_profile, select_profile_evidence
    from human_positioning import evidence_capability_score
    from role_editing import detect_role_editing_category


CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}
BUILDER_IDS = {"campaignos", "career_catalyst", "roboxt_studios"}
PERSONAL_EVIDENCE_IDS = BUILDER_IDS | {"photography_creative_voice", "substack"}
DEFAULT_MAX_CARDS = 4

_STOP_WORDS = {
    "and", "the", "for", "with", "from", "that", "this", "into", "across",
    "role", "work", "team", "teams", "will", "your", "our", "their", "using",
}
_DIMENSION_SIGNALS = {
    "leadership": ("led", "leadership", "directed", "owned", "ownership", "managed", "head", "developed talent"),
    "outcomes": ("result", "reduced", "increased", "improved", "launched", "achieved", "%", "$"),
    "business_impact": ("business impact", "revenue", "cost", "efficiency", "quality", "risk", "customer", "community impact"),
    "scale": ("enterprise", "global", "company-wide", "cross-functional", "business units", "client", "60+", "100%"),
    "transformation": ("transform", "change management", "redesign", "standardized", "scalable", "adoption", "operating model"),
    "people": ("people leadership", "talent", "developed", "mentored", "trained", "champion network", "office hours"),
    "stakeholders": ("executive", "client", "senior stakeholder", "partner", "leadership team"),
}
def _tokens(value: Any) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _project_text(project: dict[str, Any], *, include_technology: bool = True) -> str:
    fields = (
        "title",
        "label",
        "short_description",
        "description",
        "employer",
        "organization",
        "client",
        "business_unit",
        "industry",
        "function",
        "project_type",
        "problem",
        "actions",
        "results",
        "notes",
    )
    values = [str(project.get(field) or "") for field in fields]
    values.extend(
        str(value)
        for field in ("skills", "tags", "proof_points", "outcomes")
        for value in project.get(field, [])
    )
    if include_technology:
        values.extend(str(value) for value in project.get("technologies", []))
    return " ".join(values).lower()


def rank_evidence_projects(
    role: dict[str, Any], projects: list[dict[str, Any]], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Rank active Evidence without mutation; cap technology's contribution.

    Leadership, outcomes, impact, and ownership deliberately carry more combined
    weight than tool-name overlap.
    """
    role_text = _role_text(role)
    role_tokens = _tokens(role_text)
    ranked: list[dict[str, Any]] = []
    for project in projects:
        if str(project.get("status") or "Active").lower() == "archived":
            continue
        text = _project_text(project)
        nontech_text = _project_text(project, include_technology=False)
        overlap = role_tokens & _tokens(nontech_text)
        dimensions = {
            name: sum(1 for signal in signals if signal in text)
            for name, signals in _DIMENSION_SIGNALS.items()
        }
        direct = min(24, len(overlap) * 3)
        leadership = min(18, dimensions["leadership"] * 6)
        outcomes = min(16, dimensions["outcomes"] * 4)
        impact = min(12, dimensions["business_impact"] * 3)
        scale = min(10, dimensions["scale"] * 3)
        transformation = min(10, dimensions["transformation"] * 3)
        people = min(8, dimensions["people"] * 3)
        stakeholders = min(8, dimensions["stakeholders"] * 3)
        domain_values = " ".join(str(project.get(k) or "") for k in ("industry", "function", "project_type", "client"))
        domain = min(8, len(role_tokens & _tokens(domain_values)) * 2)
        technologies = " ".join(map(str, project.get("technologies", []))).lower()
        technology = min(6, len(role_tokens & _tokens(technologies)) * 2)
        score = min(100, direct + leadership + outcomes + impact + scale + transformation + people + stakeholders + domain + technology)
        reasons: list[str] = []
        reason_candidates = (
            (leadership, "Leadership / ownership match"),
            (outcomes, "Measurable business outcome"),
            (transformation, "Transformation ownership"),
            (people, "People development"),
            (stakeholders, "Executive / client stakeholder credibility"),
            (scale, "Enterprise / organizational scale"),
            (domain, "Industry and functional relevance"),
            (direct, "Direct requirement match"),
            (technology, "Technology / platform relevance"),
        )
        reasons.extend(label for value, label in sorted(reason_candidates, reverse=True) if value > 0)
        if overlap and len(reasons) < 2:
            reasons.append("Transferable functional relevance")
        if technology and len(reasons) < 2:
            reasons.append("Direct platform requirement match")
        if score <= 0:
            continue
        ranked.append({"project": project, "project_id": str(project.get("id") or ""),
                       "title": str(project.get("title") or project.get("label") or "Untitled Evidence"),
                       "score": score, "reasons": reasons[:4],
                       "dimensions": {**dimensions, "technology": technology, "direct": direct}})
    ranked.sort(key=lambda item: (-item["score"], item["title"].lower(), item["project_id"]))
    return ranked[:max(0, limit)]


def candidate_positioning_narrative(role: dict[str, Any], ranked: list[dict[str, Any]]) -> str:
    """Build an internal, Evidence-grounded positioning statement."""
    evidence_text = " ".join(_project_text(item["project"]) for item in ranked[:5])
    if not evidence_text:
        return "No active Evidence is available to support a candidate positioning statement."
    attributes: list[str] = []
    if any(term in evidence_text for term in ("led", "leadership", "owned", "directed")):
        attributes.append("leader")
    if any(term in evidence_text for term in ("transform", "change management", "redesign", "scalable")):
        attributes.append("who leads transformation and builds scalable operating systems")
    elif any(term in evidence_text for term in ("workflow", "governance", "operational")):
        attributes.append("who builds practical operating systems")
    if any(term in evidence_text for term in ("talent", "mentored", "trained", "champion network")):
        attributes.append("develops people")
    if any(term in evidence_text for term in ("executive", "client", "stakeholder")):
        attributes.append("aligns executive and client stakeholders")
    domain = "entertainment operations" if any(term in evidence_text for term in ("entertainment", "disney", "media")) else "operations"
    if any(term in evidence_text for term in ("ai", "automation", "product thinking")) and any(term in _role_text(role) for term in ("ai", "product", "technology")):
        domain = "AI-enabled operations and product"
    return (domain.capitalize() + " " + ", ".join(attributes[:3]) + ".").replace("  ", " ")


def job_requirement_coverage(role: dict[str, Any], ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map major role requirements to supporting Evidence, without filling gaps."""
    requirements = role.get("requirements")
    if isinstance(requirements, str):
        requirements = [line.strip(" -•\t") for line in requirements.splitlines() if line.strip(" -•\t")]
    if not isinstance(requirements, list) or not requirements:
        raw = str(role.get("job_description") or role.get("raw_text") or "")
        requirements = [part.strip(" -•\t") for part in re.split(r"[\n.;]+", raw) if len(part.split()) >= 3][:10]
    coverage: list[dict[str, Any]] = []
    for requirement in requirements:
        requirement = str(requirement).strip()
        tokens = _tokens(requirement)
        supporters = []
        best = 0
        for item in ranked:
            matched = tokens & _tokens(_project_text(item["project"]))
            strength = len(matched)
            if strength:
                supporters.append(item["title"])
                best = max(best, strength)
        status = "Strongly supported" if best >= 3 else "Partially supported" if best else "Unsupported"
        coverage.append({"requirement": requirement, "status": status, "evidence_projects": supporters[:3]})
    return coverage


def seniority_erosion_warnings(content: str, selected_projects: list[dict[str, Any]]) -> list[str]:
    """Flag down-leveling patterns without rewriting generated claims."""
    lowered = str(content or "").lower()
    evidence = " ".join(_project_text(project) for project in selected_projects)
    warnings: list[str] = []
    support_count = len(re.findall(r"\bsupport(?:ed|ing)?\b", lowered))
    coordinate_count = len(re.findall(r"\bcoordinat(?:e|ed|ing|ion)\b", lowered))
    if support_count >= 3:
        warnings.append("Seniority risk: support language is overused.")
    if coordinate_count >= 3:
        warnings.append("Seniority risk: coordination language is overused.")
    if any(term in evidence for term in _DIMENSION_SIGNALS["leadership"]) and not any(term in lowered for term in ("led", "leader", "owned", "directed", "managed")):
        warnings.append("Seniority risk: selected leadership or ownership Evidence is not represented.")
    if any(term in evidence for term in _DIMENSION_SIGNALS["people"]) and not any(term in lowered for term in ("talent", "developed", "mentored", "trained", "team")):
        warnings.append("Seniority risk: relevant people-development Evidence is omitted.")
    if any(term in evidence for term in _DIMENSION_SIGNALS["scale"]) and not any(term in lowered for term in ("enterprise", "client", "global", "company-wide", "cross-functional")):
        warnings.append("Seniority risk: enterprise or client scale is flattened into task execution.")
    if any(term in evidence for term in _DIMENSION_SIGNALS["transformation"]) and not any(term in lowered for term in ("transformed", "transformation", "redesigned", "standardized", "scaled", "change")):
        warnings.append("Seniority risk: transformation ownership is not represented.")
    if any(term in evidence for term in ("owned", "led", "directed")) and any(term in lowered for term in ("assisted with", "helped with", "provided support")):
        warnings.append("Seniority risk: owned work is described as assistance.")
    return warnings


def load_evidence_projects(
    project_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load optional project-style Evidence without requiring runtime data."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "data" / "evidence_projects.yml"
    if not path.is_file():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvidenceEngineError(f"Unable to read Evidence projects: {error}") from error
    projects = loaded.get("projects") if isinstance(loaded, dict) else loaded
    return [dict(item) for item in projects or [] if isinstance(item, dict)]


def evidence_projects_for_role(
    application: dict[str, Any], project_root: str | Path | None = None
) -> list[dict[str, Any]]:
    """Return only the manually associated Evidence projects, in saved order."""
    by_id = {
        str(project.get("id") or ""): project
        for project in load_evidence_projects(project_root)
    }
    return [
        by_id[str(project_id)]
        for project_id in application.get("evidence_project_ids") or []
        if str(project_id) in by_id
    ]


class EvidenceEngineError(Exception):
    """Raised when evidence cards are missing or malformed."""


def load_evidence_cards(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Load configured evidence cards and validate required fields."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "config" / "evidence_cards.yml"
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvidenceEngineError(f"Unable to read evidence cards: {error}") from error
    cards = loaded.get("evidence_cards") if isinstance(loaded, dict) else None
    if not isinstance(cards, list):
        raise EvidenceEngineError("config/evidence_cards.yml must contain evidence_cards list")
    required = {
        "id",
        "label",
        "short_description",
        "proof_points",
        "tags",
        "strongest_role_fits",
        "when_to_use",
        "when_to_avoid",
        "confidence_level",
        "source",
    }
    for card in cards:
        missing = required - set(card)
        if missing:
            raise EvidenceEngineError(f"Evidence card {card.get('id', '<unknown>')} missing {sorted(missing)}")
        if card["confidence_level"] not in CONFIDENCE_ORDER:
            raise EvidenceEngineError(f"Evidence card {card['id']} has invalid confidence_level")
    return cards


def _role_text(role: dict[str, Any]) -> str:
    values = [
        role.get("job_title"),
        role.get("title"),
        role.get("company"),
        role.get("category"),
        role.get("role_family"),
        role.get("seniority"),
        role.get("source_notes"),
        role.get("inferred_strategic_angle"),
        role.get("raw_text"),
        role.get("job_description"),
        " ".join(str(v) for v in role.get("keywords", []) if v),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _signals(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def role_evidence_category(role: dict[str, Any]) -> str:
    """Infer the evidence-selection category from role metadata and description."""
    if str(role.get("primary_role_lens") or "") == "people_operations":
        return "people_operations"
    editing_category = detect_role_editing_category(role)
    if editing_category == "chief_of_staff_business_operations":
        return "chief_of_staff_business_operations"
    if editing_category == "product_ai_operations":
        return "product_ai_operations"
    if editing_category == "marketing_operations_entertainment":
        return "entertainment_marketing_operations"
    if editing_category == "traditional_pmo_governance":
        return "traditional_pmo"
    text = _role_text(role)
    if _signals(text, ("human agency", "builder", "founder", "startup", "ai workflow", "automation", "entrepreneur")) >= 2:
        return "builder_friendly"
    if _signals(text, ("pmo", "program management office", "governance", "delivery", "risk", "qa", "executive reporting")) >= 2:
        return "traditional_pmo"
    if _signals(text, ("martech", "crm", "lifecycle", "adtech", "ad tech", "marketing technology", "measurement")):
        return "martech_crm"
    if _signals(text, ("creative operations", "content", "editorial", "storytelling", "photography", "creative production")):
        return "creative_operations"
    if _signals(text, ("entertainment", "marketing operations", "campaign", "disney", "streaming", "theatrical")) >= 2:
        return "entertainment_marketing_operations"
    return "general_operations"


def select_evidence_cards(
    role: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
    *,
    max_cards: int = DEFAULT_MAX_CARDS,
    minimum_confidence: str = "medium",
    include_personal_projects: bool = False,
) -> list[dict[str, Any]]:
    """Select role evidence; personal projects require an explicit opt-in."""
    cards = cards if cards is not None else load_evidence_cards()
    category = role_evidence_category(role)
    text = _role_text(role)
    interpretation = role.get("role_interpretation") or {}
    archetype = str(interpretation.get("primary_archetype") or "") if isinstance(interpretation, dict) else ""
    interpreted_priorities = set(evidence_priorities(archetype)) if archetype else set()
    minimum = CONFIDENCE_ORDER[minimum_confidence]
    category_tags = {
        "people_operations": {"team_leadership", "team_enablement", "change_adoption", "employee_communication", "ownership_clarity", "usable_standards", "cross_functional_leadership"},
        "chief_of_staff_business_operations": {"governance", "qa", "pmo", "cross_functional_leadership", "ambiguity_reduction"},
        "product_ai_operations": {"builder", "ai_workflows", "product_thinking", "systems_built", "governance", "ambiguity_reduction"},
        "builder_friendly": {"builder", "ai_workflows", "product_thinking", "systems_built", "ambiguity_reduction"},
        "traditional_pmo": {"governance", "qa", "pmo", "cross_functional_leadership", "ambiguity_reduction"},
        "martech_crm": {"martech", "adtech", "campaign_execution", "measurement", "product_thinking"},
        "creative_operations": {"creative_operations", "creative_work", "storytelling", "editorial", "interesting_project", "cross_functional_leadership"},
        "entertainment_marketing_operations": {"entertainment_marketing_operations", "campaign_execution", "cross_functional_leadership", "measurable_impact", "governance"},
        "general_operations": {"cross_functional_leadership", "governance", "systems_built", "ambiguity_reduction"},
    }[category]
    selected: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        card_id = str(card["id"])
        if not include_personal_projects and card_id in PERSONAL_EVIDENCE_IDS:
            continue
        confidence = CONFIDENCE_ORDER[str(card["confidence_level"])]
        if confidence < minimum:
            continue
        if category in {"traditional_pmo", "chief_of_staff_business_operations"} and card_id in {"roboxt_studios", "photography_creative_voice", "career_catalyst"}:
            continue
        if category not in {"builder_friendly", "martech_crm", "product_ai_operations", "chief_of_staff_business_operations"} and card_id in {"campaignos", "career_catalyst", "roboxt_studios"}:
            continue
        if category == "chief_of_staff_business_operations" and card_id == "campaignos" and "campaignos" not in text and _signals(text, ("ai", "automation", "product", "systems")) == 0:
            continue
        tags = set(card.get("tags", []))
        category_overlap = len(tags & category_tags)
        interpretation_overlap = len(tags & interpreted_priorities)
        interpretation_text_overlap = _signals(
            " ".join(
                [
                    str(card.get("short_description") or ""),
                    " ".join(str(value) for value in card.get("strongest_role_fits", [])),
                    " ".join(str(value) for value in card.get("proof_points", [])),
                ]
            ).lower(),
            tuple(interpreted_priorities),
        )
        role_signal_score = _signals(text, tuple(str(tag).replace("_", " ") for tag in tags))
        score = (
            category_overlap * 3
            + interpretation_overlap * 5
            + interpretation_text_overlap * 3
            + confidence
            + role_signal_score
        )
        if category_overlap or role_signal_score:
            score += min(6, evidence_capability_score(card) // 3)
        if category == "builder_friendly" and card_id in BUILDER_IDS:
            score += 5
        if category == "entertainment_marketing_operations" and card_id == "omg23_disney_leadership":
            score += 5
        if category == "traditional_pmo" and card_id == "governance_qa_delivery":
            score += 5
        if category == "chief_of_staff_business_operations" and card_id in {"governance_qa_delivery", "omg23_disney_leadership"}:
            score += 5
        if category == "people_operations" and card_id in {
            "omg23_disney_leadership",
            "governance_qa_delivery",
            "multiverse_editorial",
        }:
            score += {
                "omg23_disney_leadership": 8,
                "governance_qa_delivery": 7,
                "multiverse_editorial": 3,
            }[card_id]
        if category == "people_operations" and card_id == "martech_campaign_execution":
            score -= 12
        if category == "product_ai_operations" and card_id == "campaignos":
            score += 6
        if archetype in {
            "Technical Solutions / Solutions Consulting",
            "Advertising Technology / Ad Operations",
            "Sales Engineering",
        } and card_id == "martech_campaign_execution":
            score += 12
        if archetype in {
            "Technical Solutions / Solutions Consulting",
            "Advertising Technology / Ad Operations",
        } and card_id == "governance_qa_delivery":
            score += 5
        if score >= 5:
            selected.append((score, card))
    selected.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [card for _, card in selected[:max_cards]]


def professional_evidence_recommendations(
    role: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
    *,
    max_cards: int = DEFAULT_MAX_CARDS,
    include_personal_projects: bool = False,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return one shared, applicant-safe evidence recommendation payload."""
    selected = select_evidence_cards(
        role,
        cards,
        max_cards=max_cards,
        include_personal_projects=include_personal_projects,
    )
    proof_points = []
    people_operations = str(role.get("primary_role_lens") or "") == "people_operations"
    for card in selected:
        points = [str(point).strip() for point in card.get("proof_points", []) if str(point).strip()]
        if points:
            if people_operations:
                safe_point = next(
                    (
                        point
                        for point in points
                        if not any(
                            term in point.lower()
                            for term in (
                                "campaign operations",
                                "platform",
                                "advertiser",
                                "measurement readiness",
                            )
                        )
                    ),
                    points[0],
                )
                proof_points.append(safe_point)
            else:
                proof_points.append(points[0])
    profile = load_evidence_profile(project_root)
    profile_evidence = select_profile_evidence(
        role, profile, usage="application_strategy", max_items=max_cards
    )
    return {
        "cards": selected,
        "ids": [str(card["id"]) for card in selected],
        "labels": [str(card["label"]) for card in selected],
        "proof_points": proof_points,
        "profile_evidence": profile_evidence,
        "profile_ids": [str(item.get("id")) for item in profile_evidence],
        "profile_proof_points": [
            str(item.get("description")) for item in profile_evidence
            if str(item.get("description") or "").strip()
        ],
    }


def load_writing_voice_profile(project_root: str | Path | None = None, level: int | None = None) -> dict[str, Any]:
    """Load the configured writing voice profile; defaults to Level 3."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "config" / "writing_voice_profiles.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    default_level = int(loaded.get("default_level", 3))
    selected_level = int(level or default_level)
    levels = loaded.get("levels", {})
    profile = dict(levels.get(selected_level) or {})
    profile.update({
        "level": selected_level,
        "default_level": default_level,
        "banned_phrases": list(loaded.get("banned_phrases", [])),
    })
    return profile
