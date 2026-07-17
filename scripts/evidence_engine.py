"""Evidence card loading and role-aware selection for generated materials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

try:
    from .human_positioning import evidence_capability_score
    from .role_editing import detect_role_editing_category
except ImportError:
    from human_positioning import evidence_capability_score
    from role_editing import detect_role_editing_category


CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}
BUILDER_IDS = {"campaignos", "career_catalyst", "roboxt_studios"}
DEFAULT_MAX_CARDS = 4


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
    minimum = CONFIDENCE_ORDER[minimum_confidence]
    category_tags = {
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
        if not include_personal_projects and card_id in BUILDER_IDS:
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
        role_signal_score = _signals(text, tuple(str(tag).replace("_", " ") for tag in tags))
        score = category_overlap * 3 + confidence + role_signal_score
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
        if category == "product_ai_operations" and card_id == "campaignos":
            score += 6
        if score >= 5:
            selected.append((score, card))
    selected.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [card for _, card in selected[:max_cards]]


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
